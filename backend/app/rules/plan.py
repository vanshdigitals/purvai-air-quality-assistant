"""Daily Protection Plan generation, AI wording integration, and persistence."""

from datetime import datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete
from sqlmodel import Session, select

from app.ai.context import build_ai_context
from app.ai.gateway import generate_plan_wording
from app.ai.schemas.v1.models import (
    ActionIdLiteral,
    AIContextPlanPeriod,
    DailyPlanWording,
)
from app.aqi.calculator import category_for_aqi
from app.aqi.pipeline import (
    AirForecastResponse,
    AirQualityResponse,
    ForecastHourOut,
    ForecastLowestOut,
    get_air_quality,
    get_hourly_forecast_points,
    parse_utc_iso,
    to_utc_iso,
    utc_now,
)
from app.config import Settings
from app.db.models import DailyPlan, Household, Location, PlanItem, SettingsRecord
from app.rules.catalogue import Category
from app.rules.engine import compute_verdict

IST_ZONE = ZoneInfo("Asia/Kolkata")
PLAN_REUSE_TTL = timedelta(minutes=30)

PLAN_PERIODS: tuple[tuple[Literal["morning", "afternoon", "evening", "night"], int, int], ...] = (
    ("morning", 6, 12),
    ("afternoon", 12, 17),
    ("evening", 17, 21),
    ("night", 21, 30),
)


class PlanItemOut(BaseModel):
    """Single item in a plan period (deterministic rule or guarded AI wording)."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    text: str
    why: str | None = None
    tag: Literal["rule", "ai_wording"] = "rule"


class PlanPeriodOut(BaseModel):
    """One of four daily plan periods."""

    model_config = ConfigDict(frozen=True)

    period: Literal["morning", "afternoon", "evening", "night"]
    start: str
    end: str
    level: Category
    aqi: int
    past: bool
    items: list[PlanItemOut]


class DailyPlanResponse(BaseModel):
    """Response model for POST /api/v1/plan."""

    model_config = ConfigDict(frozen=True)

    plan_date: str
    day: Literal["today", "tomorrow"]
    generated_by: Literal["rules", "gemini", "groq", "template"] = "rules"
    generated_at: str
    source_label: Literal["Measured", "Modelled", "Estimated"]
    summary: str | None = None
    note: str | None = None
    periods: list[PlanPeriodOut]


def _can_reuse_existing_plan(
    *,
    existing_plan: DailyPlan | None,
    stored_items: list[PlanItem],
    periods_rule_data: list[dict[str, Any]],
    now_utc: datetime,
    rebuild: bool,
    ai_will_run: bool,
) -> bool:
    if rebuild or existing_plan is None:
        return False
    age = now_utc - parse_utc_iso(existing_plan.created_at)
    if age >= PLAN_REUSE_TTL:
        return False
    if ai_will_run and existing_plan.generated_by == "rules":
        return False
    if not ai_will_run and existing_plan.generated_by in ("gemini", "groq"):
        return False

    stored_by_period: dict[str, list[str]] = {}
    for row in stored_items:
        stored_by_period.setdefault(row.period, []).append(row.action_id)

    for p_data in periods_rule_data:
        if p_data["past"]:
            if stored_by_period.get(p_data["period"], []):
                return False
        else:
            expected_ids = [item.action_id for item in p_data["rule_items"]]
            if stored_by_period.get(p_data["period"], []) != expected_ids:
                return False
    return True


async def build_daily_plan(
    session: Session,
    *,
    settings: Settings,
    household: Household,
    member_kinds: list[str],
    location: Location,
    day: Literal["today", "tomorrow"],
    rebuild: bool = False,
    household_header: str | None = None,
    plan_ai_cache: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> DailyPlanResponse:
    """Compute, optionally AI-word under guard, and persist the 4-period Daily Protection Plan."""
    now_utc = utc_now()
    now_ist = now_utc.astimezone(IST_ZONE)
    target_date = now_ist.date() if day == "today" else (now_ist.date() + timedelta(days=1))
    day_midnight_ist = datetime(
        target_date.year, target_date.month, target_date.day, tzinfo=IST_ZONE
    )

    forecast_hours, obs_id = await get_hourly_forecast_points(
        session,
        settings=settings,
        lat=location.lat,
        lon=location.lon,
        now=now_utc,
    )

    air_obj: AirQualityResponse | None = None
    current_aqi: int | None = None
    source_label: Literal["Measured", "Modelled", "Estimated"] = "Modelled"
    if day == "today":
        air_obj = await get_air_quality(
            session,
            settings=settings,
            lat=location.lat,
            lon=location.lon,
            household_header=household_header,
        )
        current_aqi = air_obj.aqi
        source_label = air_obj.source_label

    ist_points: list[tuple[datetime, ForecastHourOut]] = [
        (parse_utc_iso(pt.time).astimezone(IST_ZONE), pt) for pt in forecast_hours
    ]

    periods_rule_data: list[dict[str, Any]] = []
    worst_plan_aqi = 0

    for period_name, start_offset_h, end_offset_h in PLAN_PERIODS:
        p_start = day_midnight_ist + timedelta(hours=start_offset_h)
        p_end = day_midnight_ist + timedelta(hours=end_offset_h)
        is_past = day == "today" and now_ist >= p_end
        is_current = day == "today" and p_start <= now_ist < p_end

        window_aqis = [pt.aqi for dt_ist, pt in ist_points if p_start <= dt_ist < p_end]
        if is_current and current_aqi is not None:
            window_aqis.append(current_aqi)

        if window_aqis:
            period_aqi = max(window_aqis)
        elif current_aqi is not None:
            period_aqi = current_aqi
        else:
            period_aqi = forecast_hours[0].aqi

        worst_plan_aqi = max(worst_plan_aqi, period_aqi)
        level = category_for_aqi(period_aqi)
        verdict = compute_verdict(level, member_kinds)
        rule_items = [
            PlanItemOut(action_id=action.action_id, text=action.text, tag="rule")
            for action in verdict.actions
        ]
        periods_rule_data.append(
            {
                "period": period_name,
                "start": f"{start_offset_h % 24:02d}:00",
                "end": f"{end_offset_h % 24:02d}:00",
                "level": level,
                "aqi": period_aqi,
                "past": is_past,
                "rule_items": rule_items,
                "action_ids": [cast(ActionIdLiteral, a.action_id) for a in verdict.actions],
            }
        )

    plan_date_str = target_date.isoformat()
    overall_level = category_for_aqi(worst_plan_aqi)

    settings_row = session.get(SettingsRecord, household.id)
    ai_enabled = bool(settings_row.ai_enabled) if settings_row is not None else True
    has_ai_key = bool(
        settings.purvai_fake_providers or settings.gemini_api_key or settings.groq_api_key
    )
    ai_will_run = ai_enabled and has_ai_key

    existing_plan = session.exec(
        select(DailyPlan).where(
            DailyPlan.household_id == household.id,
            DailyPlan.plan_date == plan_date_str,
        )
    ).first()
    stored_items: list[PlanItem] = []
    if existing_plan is not None and existing_plan.id is not None:
        stored_items = list(
            session.exec(select(PlanItem).where(PlanItem.plan_id == existing_plan.id)).all()
        )

    if (
        existing_plan is not None
        and _can_reuse_existing_plan(
            existing_plan=existing_plan,
            stored_items=stored_items,
            periods_rule_data=periods_rule_data,
            now_utc=now_utc,
            rebuild=rebuild,
            ai_will_run=ai_will_run,
        )
        and existing_plan.verdict_level == overall_level
    ):
        cached_meta = (
            plan_ai_cache.get((household.id, plan_date_str, existing_plan.created_at), {})
            if plan_ai_cache is not None
            else {}
        )
        whys_by_key: dict[tuple[str, str], str] = cached_meta.get("whys", {})
        items_by_period: dict[str, list[PlanItem]] = {}
        for row in stored_items:
            items_by_period.setdefault(row.period, []).append(row)

        reused_periods: list[PlanPeriodOut] = []
        for p_data in periods_rule_data:
            p_name = p_data["period"]
            if p_data["past"]:
                out_items: list[PlanItemOut] = []
            else:
                out_items = [
                    PlanItemOut(
                        action_id=row.action_id,
                        text=row.text,
                        why=whys_by_key.get((p_name, row.action_id)),
                        tag="ai_wording" if row.tag == "ai_wording" else "rule",
                    )
                    for row in items_by_period.get(p_name, [])
                ]
            reused_periods.append(
                PlanPeriodOut(
                    period=p_name,
                    start=p_data["start"],
                    end=p_data["end"],
                    level=p_data["level"],
                    aqi=p_data["aqi"],
                    past=p_data["past"],
                    items=out_items,
                )
            )
        gen_by = cast(
            Literal["rules", "gemini", "groq", "template"],
            existing_plan.generated_by,
        )
        return DailyPlanResponse(
            plan_date=plan_date_str,
            day=day,
            generated_by=gen_by,
            generated_at=existing_plan.created_at,
            source_label=source_label,
            summary=cached_meta.get("summary"),
            note=cached_meta.get("note"),
            periods=reused_periods,
        )

    generated_by: Literal["rules", "gemini", "groq", "template"] = "rules"
    summary: str | None = None
    note: str | None = None
    ai_wording_by_period: dict[str, dict[str, tuple[str, str]]] = {}

    if ai_will_run:
        if air_obj is None:
            air_obj = await get_air_quality(
                session,
                settings=settings,
                lat=location.lat,
                lon=location.lon,
                household_header=household_header,
            )
        upcoming = forecast_hours[:12]
        lowest_pt = min(upcoming, key=lambda h: h.aqi)
        forecast_resp = AirForecastResponse(
            scale="CPCB_NAQI",
            source_label="Modelled",
            indicative=True,
            attribution=["Open-Meteo", "CAMS"],
            generated_at=to_utc_iso(now_utc),
            hours=upcoming,
            lowest=ForecastLowestOut(
                time=lowest_pt.time,
                aqi=lowest_pt.aqi,
                category=category_for_aqi(lowest_pt.aqi),
            ),
        )
        plan_context_periods = [
            AIContextPlanPeriod(
                period=p["period"],
                level=p["level"],
                aqi=p["aqi"],
                action_ids=p["action_ids"],
            )
            for p in periods_rule_data
        ]
        # Ground overall verdict level on worst plan verdict for strict consistency
        overall_verdict = compute_verdict(overall_level, member_kinds)
        plan_air = air_obj.model_copy(
            update={
                "aqi": worst_plan_aqi,
                "category": overall_level,
                "verdict": overall_verdict,
            }
        )
        context = build_ai_context(
            air=plan_air,
            forecast=forecast_resp,
            member_kinds=member_kinds,
            city=location.city,
            now_utc=now_utc,
            plan_periods=plan_context_periods,
        )
        gw = await generate_plan_wording(
            settings=settings,
            context=context,
            ai_enabled=True,
        )
        if gw.generated_by in ("gemini", "groq"):
            assert isinstance(gw.data, DailyPlanWording)
            generated_by = gw.generated_by
            summary = gw.data.summary
            for wp in gw.data.periods:
                ai_wording_by_period[wp.period] = {
                    rec.action_id: (rec.title[:60], rec.why[:200]) for rec in wp.items
                }
        else:
            generated_by = "template"
            note = gw.note

    periods_out: list[PlanPeriodOut] = []
    whys_cache: dict[tuple[str, str], str] = {}
    for p_data in periods_rule_data:
        p_name = p_data["period"]
        if p_data["past"]:
            items: list[PlanItemOut] = []
        else:
            if generated_by in ("gemini", "groq") and p_name in ai_wording_by_period:
                period_map = ai_wording_by_period[p_name]
                items = []
                for rule_item in p_data["rule_items"]:
                    title_why = period_map.get(rule_item.action_id)
                    if title_why is not None:
                        title_txt, why_txt = title_why
                        whys_cache[(p_name, rule_item.action_id)] = why_txt
                        items.append(
                            PlanItemOut(
                                action_id=rule_item.action_id,
                                text=title_txt,
                                why=why_txt,
                                tag="ai_wording",
                            )
                        )
                    else:
                        items.append(rule_item)
            else:
                items = p_data["rule_items"]

        periods_out.append(
            PlanPeriodOut(
                period=p_name,
                start=p_data["start"],
                end=p_data["end"],
                level=p_data["level"],
                aqi=p_data["aqi"],
                past=p_data["past"],
                items=items,
            )
        )

    generated_at_iso = to_utc_iso(now_utc)
    if existing_plan is None:
        plan_row = DailyPlan(
            household_id=household.id,
            plan_date=plan_date_str,
            verdict_level=overall_level,
            aqi_observation_id=obs_id,
            generated_by=generated_by,
            created_at=generated_at_iso,
        )
        session.add(plan_row)
        session.flush()
    else:
        existing_plan.verdict_level = overall_level
        existing_plan.aqi_observation_id = obs_id
        existing_plan.generated_by = generated_by
        existing_plan.created_at = generated_at_iso
        session.exec(delete(PlanItem).where(PlanItem.plan_id == existing_plan.id))  # type: ignore[arg-type]
        plan_row = existing_plan
        session.flush()

    assert plan_row.id is not None
    for period_out in periods_out:
        for item in period_out.items:
            session.add(
                PlanItem(
                    plan_id=plan_row.id,
                    period=period_out.period,
                    action_id=item.action_id,
                    text=item.text,
                    tag=item.tag,
                )
            )
    session.commit()

    if plan_ai_cache is not None:
        plan_ai_cache[(household.id, plan_date_str, generated_at_iso)] = {
            "summary": summary,
            "note": note,
            "whys": whys_cache,
        }

    return DailyPlanResponse(
        plan_date=plan_date_str,
        day=day,
        generated_by=generated_by,
        generated_at=generated_at_iso,
        source_label=source_label,
        summary=summary,
        note=note,
        periods=periods_out,
    )
