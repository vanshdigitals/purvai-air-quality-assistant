"""Data export and import endpoints (FR-14)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete
from sqlmodel import Session, select

from app.api.errors import ApiStatusError
from app.api.household import (
    MemberIn,
    SettingsIn,
    _find_household,
    parse_demo_household_header,
    resolve_existing_household,
)
from app.aqi.pipeline import to_utc_iso, utc_now
from app.db.models import (
    ActivityLog,
    Household,
    Location,
    Member,
    SettingsRecord,
    utc_now_iso,
)
from app.impact.factors import get_factor

router = APIRouter()

MAX_IMPORT_BYTES = 5 * 1024 * 1024


class ImportActivityIn(BaseModel):
    """Single activity item in JSON import payload."""

    model_config = ConfigDict(extra="ignore")

    kind: str = Field(min_length=1, max_length=40)
    mode: str | None = None
    replaced_mode: str | None = None
    distance_km: float | None = Field(default=None, ge=0.0, le=500.0)
    hours: float | None = Field(default=None, ge=0.0, le=24.0)
    co2_saved_g: float | None = Field(default=None, ge=0.0)
    occurred_at: str | None = None


class ImportLocationIn(BaseModel):
    """Location item in JSON import payload."""

    model_config = ConfigDict(extra="ignore")

    label: str = Field(min_length=1, max_length=60)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    city: str | None = Field(default=None, max_length=120)
    is_primary: bool = False


class ImportHouseholdIn(BaseModel):
    """Household section in JSON import payload."""

    model_config = ConfigDict(extra="ignore")

    members: list[MemberIn] = Field(min_length=1)
    locations: list[ImportLocationIn] = Field(min_length=1)
    settings: SettingsIn


class DataExportPayload(BaseModel):
    """Schema v1 export/import envelope."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = Field(alias="schema")
    exported_at: str | None = None
    household: ImportHouseholdIn
    activities: list[ImportActivityIn] = Field(default_factory=list)


@router.get("/data/export")
async def export_data(request: Request) -> JSONResponse:
    """Export household, locations, settings, and activities as schema v1 JSON."""
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        members = session.exec(select(Member).where(Member.household_id == household.id)).all()
        locations = session.exec(
            select(Location).where(Location.household_id == household.id)
        ).all()
        settings_row = session.exec(
            select(SettingsRecord).where(SettingsRecord.household_id == household.id)
        ).first()
        activities = session.exec(
            select(ActivityLog).where(ActivityLog.household_id == household.id)
        ).all()

        payload: dict[str, Any] = {
            "schema": 1,
            "exported_at": utc_now_iso(),
            "household": {
                "members": [{"kind": m.kind, "count": m.count} for m in members],
                "locations": [
                    {
                        "label": loc.label,
                        "lat": loc.lat,
                        "lon": loc.lon,
                        "city": loc.city,
                        "is_primary": loc.is_primary,
                    }
                    for loc in locations
                ],
                "settings": {
                    "theme": settings_row.theme if settings_row else "system",
                    "commute_mode": settings_row.commute_mode if settings_row else "metro",
                    "ai_enabled": settings_row.ai_enabled if settings_row else True,
                    "save_chat": settings_row.save_chat if settings_row else False,
                    "reduce_motion": settings_row.reduce_motion if settings_row else False,
                },
            },
            "activities": [
                {
                    "kind": act.kind,
                    "mode": act.mode,
                    "replaced_mode": act.replaced_mode,
                    "distance_km": act.distance_km,
                    "hours": act.hours,
                    "co2_saved_g": act.co2_saved_g,
                    "occurred_at": act.occurred_at,
                }
                for act in activities
            ],
        }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="purvai-export.json"'},
    )


@router.post("/data/import")
async def import_data(request: Request, dry_run: bool = False) -> dict[str, Any]:
    """Validate and optionally import a schema v1 JSON bundle in one transaction."""
    raw = await request.body()
    if len(raw) > MAX_IMPORT_BYTES:
        raise ApiStatusError(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="PAYLOAD_TOO_LARGE",
            message="Import payload exceeds 5 MB limit.",
        )

    try:
        parsed_raw = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiStatusError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="VALIDATION_ERROR",
            message=f"Invalid JSON payload: {exc}",
        ) from exc

    if not isinstance(parsed_raw, dict) or parsed_raw.get("schema") != 1:
        raise ApiStatusError(
            status_code=status.HTTP_409_CONFLICT,
            code="SCHEMA_MISMATCH",
            message="Unsupported or missing schema version; expected schema=1.",
        )

    try:
        bundle = DataExportPayload.model_validate(parsed_raw)
    except ValidationError as exc:
        raise ApiStatusError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="VALIDATION_ERROR",
            message=str(exc.errors()[0].get("msg", "Invalid import payload")),
        ) from exc

    counts = {
        "members": len(bundle.household.members),
        "locations": len(bundle.household.locations),
        "activities": len(bundle.activities),
    }
    if dry_run:
        return {"dry_run": True, "counts": counts}

    settings = request.app.state.settings
    engine = request.app.state.engine
    now_iso = to_utc_iso(utc_now())

    with Session(engine) as session:
        demo_id = parse_demo_household_header(request) if settings.purvai_mode == "demo" else None
        household = _find_household(
            session,
            mode=settings.purvai_mode,
            demo_id=demo_id,
            now_iso=now_iso,
        )
        if household is None:
            household = Household(mode=settings.purvai_mode, created_at=now_iso, updated_at=now_iso)
            session.add(household)
            session.flush()
        else:
            household.updated_at = now_iso
            session.exec(delete(Member).where(Member.household_id == household.id))  # type: ignore[arg-type]
            session.exec(delete(Location).where(Location.household_id == household.id))  # type: ignore[arg-type]
            session.exec(
                delete(SettingsRecord).where(SettingsRecord.household_id == household.id)  # type: ignore[arg-type]
            )
            session.exec(delete(ActivityLog).where(ActivityLog.household_id == household.id))  # type: ignore[arg-type]

        for m in bundle.household.members:
            session.add(Member(household_id=household.id, kind=m.kind, count=m.count))

        has_primary = any(loc.is_primary for loc in bundle.household.locations)
        for idx, loc in enumerate(bundle.household.locations):
            session.add(
                Location(
                    household_id=household.id,
                    label=loc.label,
                    lat=loc.lat,
                    lon=loc.lon,
                    city=loc.city,
                    is_primary=loc.is_primary if has_primary else (idx == 0),
                )
            )

        s = bundle.household.settings
        session.add(
            SettingsRecord(
                household_id=household.id,
                theme=s.theme,
                commute_mode=s.commute_mode,
                ai_enabled=s.ai_enabled,
                save_chat=s.save_chat,
                reduce_motion=s.reduce_motion,
            )
        )

        for act in bundle.activities:
            factor = get_factor(session, act.mode) if act.mode else None
            session.add(
                ActivityLog(
                    household_id=household.id,
                    kind=act.kind,
                    mode=act.mode,
                    replaced_mode=act.replaced_mode,
                    distance_km=act.distance_km,
                    hours=act.hours,
                    factor_id=factor.id if factor else None,
                    co2_saved_g=act.co2_saved_g,
                    occurred_at=act.occurred_at or now_iso,
                )
            )

        session.commit()

    return {"dry_run": False, "imported": counts}
