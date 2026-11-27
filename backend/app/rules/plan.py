"""Daily Protection Plan generation and persistence (rules-only in Phase 3)."""

from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete
from sqlmodel import Session, select

from app.aqi.calculator import category_for_aqi
from app.aqi.pipeline import (
    ForecastHourOut,
    get_air_quality,
    get_hourly_forecast_points,
    parse_utc_iso,
    to_utc_iso,
    utc_now,
)
from app.config import Settings
from app.db.models import DailyPlan, Household, Location, PlanItem
from app.rules.catalogue import Category
from app.rules.engine import compute_verdict

IST_ZONE = ZoneInfo("Asia/Kolkata")

PLAN_PERIODS: tuple[tuple[Literal["morning", "afternoon", "evening", "night"], int, int], ...] = (
    ("morning", 6, 12),
    ("afternoon", 12, 17),
    ("evening", 17, 21),
    ("night", 21, 30),
)


class PlanItemOut(BaseModel):
    """Single deterministic rule item in a plan period."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    text: str
    tag: Literal["rule"] = "rule"


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
    generated_by: Literal["rules"] = "rules"
    generated_at: str
    source_label: Literal["Measured", "Modelled", "Estimated"]
    periods: list[PlanPeriodOut]


async def build_daily_plan(
    session: Session,
    *,
    settings: Settings,
    household: Household,
    member_kinds: list[str],
    location: Location,
    day: Literal["today", "tomorrow"],
    household_header: str | None = None,
) -> DailyPlanResponse:
    """Compute and persist the 4-period Daily Protection Plan for today or tomorrow."""
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

    current_aqi: int | None = None
    source_label: Literal["Measured", "Modelled", "Estimated"] = "Modelled"
    if day == "today":
        air = await get_air_quality(
            session,
            settings=settings,
            lat=location.lat,
            lon=location.lon,
            household_header=household_header,
        )
        current_aqi = air.aqi
        source_label = air.source_label

    # Map forecast hours to IST once
    ist_points: list[tuple[datetime, ForecastHourOut]] = [
        (parse_utc_iso(pt.time).astimezone(IST_ZONE), pt) for pt in forecast_hours
    ]

    periods_out: list[PlanPeriodOut] = []
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

        if is_past:
            items: list[PlanItemOut] = []
        else:
            verdict = compute_verdict(level, member_kinds)
            items = [
                PlanItemOut(action_id=action.action_id, text=action.text, tag="rule")
                for action in verdict.actions
            ]

        periods_out.append(
            PlanPeriodOut(
                period=period_name,
                start=f"{start_offset_h % 24:02d}:00",
                end=f"{end_offset_h % 24:02d}:00",
                level=level,
                aqi=period_aqi,
                past=is_past,
                items=items,
            )
        )

    plan_date_str = target_date.isoformat()
    generated_at_iso = to_utc_iso(now_utc)
    overall_level = category_for_aqi(worst_plan_aqi)

    existing_plan = session.exec(
        select(DailyPlan).where(
            DailyPlan.household_id == household.id,
            DailyPlan.plan_date == plan_date_str,
        )
    ).first()

    if existing_plan is None:
        plan_row = DailyPlan(
            household_id=household.id,
            plan_date=plan_date_str,
            verdict_level=overall_level,
            aqi_observation_id=obs_id,
            generated_by="rules",
            created_at=generated_at_iso,
        )
        session.add(plan_row)
        session.flush()
    else:
        existing_plan.verdict_level = overall_level
        existing_plan.aqi_observation_id = obs_id
        existing_plan.generated_by = "rules"
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
                    tag="rule",
                )
            )
    session.commit()

    return DailyPlanResponse(
        plan_date=plan_date_str,
        day=day,
        generated_by="rules",
        generated_at=generated_at_iso,
        source_label=source_label,
        periods=periods_out,
    )
