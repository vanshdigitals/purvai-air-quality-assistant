"""Activity log and CO₂ impact endpoints (FR-11)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.api.errors import ApiStatusError
from app.api.household import resolve_existing_household
from app.db.models import ActivityLog
from app.impact import service as svc

router = APIRouter()

CommuteModeOrNone = Literal[
    "metro",
    "bus",
    "car",
    "cycle",
    "walk",
    "scooter",
    "auto",
    "none",
    "car_petrol",
    "motorcycle",
    "auto_cng",
    "auto_diesel",
    "bus_diesel",
    "bus_diesel_ac",
    "bus_cng",
]


class ActivityIn(BaseModel):
    """Body for POST /api/v1/activities."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=40)
    mode: CommuteModeOrNone | None = None
    replaced_mode: CommuteModeOrNone | None = None
    distance_km: float | None = Field(default=None, ge=0.0, le=500.0)
    hours: float | None = Field(default=None, ge=0.0, le=24.0)
    occurred_at: str | None = Field(default=None, max_length=32)


class ActivityOut(BaseModel):
    """Single activity log entry in API responses."""

    model_config = ConfigDict(extra="forbid")

    id: int
    kind: str
    mode: str | None
    replaced_mode: str | None
    distance_km: float | None
    hours: float | None
    co2_saved_g: float | None
    occurred_at: str


def _to_out(row: ActivityLog) -> ActivityOut:
    return ActivityOut(
        id=row.id or 0,
        kind=row.kind,
        mode=row.mode,
        replaced_mode=row.replaced_mode,
        distance_km=row.distance_km,
        hours=row.hours,
        co2_saved_g=row.co2_saved_g,
        occurred_at=row.occurred_at,
    )


@router.post(
    "/activities",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_activity(request: Request, body: ActivityIn) -> ActivityOut:
    """Log a commute or outdoor-exposure activity for the household."""
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        row = svc.log_activity(
            session,
            household,
            kind=body.kind,
            mode=body.mode,
            replaced_mode=body.replaced_mode,
            distance_km=body.distance_km,
            hours=body.hours,
            occurred_at=body.occurred_at,
        )
        return _to_out(row)


@router.get("/activities", response_model=list[ActivityOut])
async def get_activities(request: Request, days: int = 7) -> list[ActivityOut]:
    """Return the household's activity log for the past *days*."""
    if days < 1 or days > 90:
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="days must be between 1 and 90.",
        )
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        rows = svc.get_activities(session, household, days=days)
        return [_to_out(r) for r in rows]


@router.delete("/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity(request: Request, activity_id: int) -> None:
    """Delete a single activity log entry owned by this household."""
    from sqlmodel import select as sel

    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        row = session.exec(
            sel(ActivityLog).where(
                ActivityLog.id == activity_id,
                ActivityLog.household_id == household.id,
            )
        ).first()
        if row is None:
            raise ApiStatusError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="NOT_FOUND",
                message=f"Activity {activity_id} not found.",
            )
        session.delete(row)
        session.commit()


@router.get("/impact/summary")
async def get_impact_summary(request: Request, days: int = 7) -> dict[str, object]:
    """Return aggregate CO₂ saved and trip counts for the past *days*."""
    if days < 1 or days > 90:
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="days must be between 1 and 90.",
        )
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        return svc.get_summary(session, household, days=days)


@router.get("/impact/compare")
async def get_impact_compare(request: Request, days: int = 7) -> dict[str, object]:
    """Compare actual CO₂ emissions against a car_petrol baseline."""
    if days < 1 or days > 90:
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="days must be between 1 and 90.",
        )
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        return svc.get_comparison(session, household, days=days)
