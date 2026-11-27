"""Derived-only AI context builder (v1.1) — zero PII, zero exact coordinates, zero past chat."""

from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from app.ai.schemas.v1.models import (
    ActionIdLiteral,
    AIContext,
    AIContextForecastPoint,
    AIContextHousehold,
    AIContextPlanPeriod,
    AIContextPollutant,
    AIContextVerdict,
    ForecastTrendLiteral,
)
from app.aqi.pipeline import AirForecastResponse, AirQualityResponse, parse_utc_iso, utc_now
from app.rules.catalogue import CATEGORY_ORDER, Category

IST_ZONE = ZoneInfo("Asia/Kolkata")


def _format_ist_hhmm(iso_utc: str) -> str:
    dt = parse_utc_iso(iso_utc).astimezone(IST_ZONE)
    return f"{dt.hour:02d}:{dt.minute:02d}"


def compute_forecast_trend(
    current_category: Category,
    forecast_categories: list[Category],
) -> ForecastTrendLiteral:
    """Compare current category with worst category across next 6 forecast hours."""
    window = forecast_categories[:6]
    if not window:
        return "steady"
    current_idx = CATEGORY_ORDER.index(current_category)
    worst_idx = max(CATEGORY_ORDER.index(cat) for cat in window)
    if worst_idx > current_idx:
        return "worsening"
    if worst_idx < current_idx:
        return "improving"
    return "steady"


def build_ai_context(
    *,
    air: AirQualityResponse,
    forecast: AirForecastResponse | None,
    member_kinds: list[str],
    city: str | None,
    now_utc: datetime | None = None,
    plan_periods: list[AIContextPlanPeriod] | None = None,
) -> AIContext:
    """Construct Context v1.1 strictly from server air/forecast/rules/household flags."""
    current = now_utc or utc_now()
    now_ist = current.astimezone(IST_ZONE)
    local_time = f"{now_ist.hour:02d}:{now_ist.minute:02d}"

    kinds = set(member_kinds)
    household_flags = AIContextHousehold(
        has_child="child_u12" in kinds,
        has_older_adult="adult_65p" in kinds,
        has_heart_lung="heart_lung" in kinds,
        outdoor_worker="outdoor_worker" in kinds,
    )

    current_cat = cast(Category, air.category)
    forecast_points: list[AIContextForecastPoint] = []
    if forecast is not None:
        forecast_points = [
            AIContextForecastPoint(
                time_ist=_format_ist_hhmm(h.time),
                aqi=h.aqi,
                category=h.category,
            )
            for h in forecast.hours[:12]
        ]

    trend = compute_forecast_trend(
        current_cat,
        [pt.category for pt in forecast_points[:6]],
    )

    pollutants = {
        pid: AIContextPollutant(value=reading.value, sub_index=reading.sub_index)
        for pid, reading in air.pollutants.items()
    }

    action_ids = [cast(ActionIdLiteral, aid) for aid in air.verdict.action_ids]

    return AIContext(
        schema_version="1.1",
        aqi=air.aqi,
        category=current_cat,
        source_label=air.source_label,
        dominant_pollutant=air.dominant_pollutant,
        forecast_trend=trend,
        grap_stage=air.grap.stage if air.grap is not None else None,
        household=household_flags,
        verdict=AIContextVerdict(
            level=air.verdict.household_level,
            action_ids=action_ids,
        ),
        local_time=local_time,
        city=city,
        stale=air.stale,
        age_minutes=air.age_minutes,
        age_hours=max(0, air.age_minutes // 60),
        observed_time_ist=_format_ist_hhmm(air.observed_at),
        pollutants=pollutants,
        forecast=forecast_points,
        plan_periods=plan_periods,
    )
