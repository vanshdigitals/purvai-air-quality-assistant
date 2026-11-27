"""CO₂ impact calculation service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, func, select

from app.db.models import ActivityLog, Household, utc_now_iso
from app.impact.factors import get_factor


def _utc_days_ago(days: int) -> str:
    """Return ISO 8601 UTC timestamp *days* ago."""
    return (datetime.now(UTC) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def log_activity(
    session: Session,
    household: Household,
    *,
    kind: str,
    mode: str | None,
    replaced_mode: str | None,
    distance_km: float | None,
    hours: float | None,
    occurred_at: str | None = None,
) -> ActivityLog:
    """Create an ActivityLog row, computing co2_saved_g when possible."""
    co2_saved_g: float | None = None
    factor_id: str | None = None

    if distance_km is not None and distance_km > 0 and mode and replaced_mode:
        chosen = get_factor(session, mode)
        baseline = get_factor(session, replaced_mode)
        if chosen is not None and baseline is not None:
            factor_id = chosen.id
            co2_saved_g = max(0.0, (baseline.g_co2e_per_pkm - chosen.g_co2e_per_pkm) * distance_km)

    entry = ActivityLog(
        household_id=household.id,
        kind=kind,
        mode=mode,
        replaced_mode=replaced_mode,
        distance_km=distance_km,
        hours=hours,
        factor_id=factor_id,
        co2_saved_g=co2_saved_g,
        occurred_at=occurred_at or utc_now_iso(),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def get_activities(
    session: Session,
    household: Household,
    *,
    days: int = 7,
) -> list[ActivityLog]:
    """Return up to *days* of ActivityLog rows, newest first."""
    since = _utc_days_ago(days)
    return list(
        session.exec(
            select(ActivityLog)
            .where(
                ActivityLog.household_id == household.id,
                ActivityLog.occurred_at >= since,
            )
            .order_by(col(ActivityLog.occurred_at).desc())
        ).all()
    )


def get_summary(
    session: Session,
    household: Household,
    *,
    days: int = 7,
) -> dict[str, object]:
    """Return aggregate CO₂ saved and trip counts for the past *days*."""
    since = _utc_days_ago(days)
    rows = session.exec(
        select(
            func.count(col(ActivityLog.id)).label("trips"),
            func.coalesce(func.sum(ActivityLog.co2_saved_g), 0.0).label("co2_saved_g"),
            func.coalesce(func.sum(ActivityLog.distance_km), 0.0).label("distance_km"),
        ).where(
            ActivityLog.household_id == household.id,
            ActivityLog.occurred_at >= since,
        )
    ).one()
    trips = int(rows[0] or 0)
    co2_saved_g = float(rows[1] or 0.0)
    distance_km = float(rows[2] or 0.0)
    return {
        "trips": trips,
        "co2_saved_g": round(co2_saved_g, 1),
        "co2_saved_kg": round(co2_saved_g / 1000, 3),
        "distance_km": round(distance_km, 2),
        "days": days,
    }


def get_comparison(
    session: Session,
    household: Household,
    *,
    days: int = 7,
) -> dict[str, object]:
    """Compare actual CO₂ with car_petrol baseline."""
    since = _utc_days_ago(days)
    rows = session.exec(
        select(ActivityLog).where(
            ActivityLog.household_id == household.id,
            ActivityLog.occurred_at >= since,
        )
    ).all()

    actual_g = 0.0
    baseline_g = 0.0
    for row in rows:
        if row.distance_km and row.mode:
            factor = get_factor(session, row.mode)
            baseline = get_factor(session, "car_petrol")
            if factor is not None and baseline is not None:
                actual_g += factor.g_co2e_per_pkm * row.distance_km
                baseline_g += baseline.g_co2e_per_pkm * row.distance_km

    saved_g = max(0.0, baseline_g - actual_g)
    return {
        "actual_g": round(actual_g, 1),
        "baseline_car_petrol_g": round(baseline_g, 1),
        "saved_vs_car_g": round(saved_g, 1),
        "saved_vs_car_kg": round(saved_g / 1000, 3),
        "days": days,
    }
