"""Data export and import endpoints (FR-14)."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
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
from app.db.engine import run_quick_check
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


_BACKUP_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.db$")


def _require_local_mode(request: Request) -> Path:
    settings = request.app.state.settings
    if settings.purvai_mode != "local":
        raise ApiStatusError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Database backup and restore are only available in local mode.",
        )
    return Path(settings.resolved_database_path)


def _backups_dir(db_path: Path) -> Path:
    bdir = db_path.parent / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    return bdir


def _sqlite_backup(src_path: Path, dst_path: Path) -> None:
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


class RestoreIn(BaseModel):
    """Body for POST /api/v1/db/restore."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=120)


class ClearDataIn(BaseModel):
    """Body for DELETE /api/v1/data."""

    model_config = ConfigDict(extra="forbid")

    confirm: str


@router.post("/db/backup")
async def create_backup(request: Request) -> dict[str, Any]:
    """Create a timestamped SQLite online backup (local mode only, keeps last 7)."""
    db_path = _require_local_mode(request)
    bdir = _backups_dir(db_path)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = bdir / f"purvai-{stamp}.db"
    counter = 1
    while target.exists():
        target = bdir / f"purvai-{stamp}-{counter}.db"
        counter += 1

    _sqlite_backup(db_path, target)

    # Keep last 7 backups
    backups = sorted(bdir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[7:]:
        old.unlink(missing_ok=True)

    return {
        "filename": target.name,
        "byte_size": target.stat().st_size,
        "created_at": utc_now_iso(),
    }


@router.get("/db/backups")
async def list_backups(request: Request) -> list[dict[str, Any]]:
    """List available local SQLite backups newest first (local mode only)."""
    db_path = _require_local_mode(request)
    bdir = _backups_dir(db_path)
    backups = sorted(bdir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "filename": p.name,
            "byte_size": p.stat().st_size,
            "created_at": datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        for p in backups
    ]


@router.post("/db/restore")
async def restore_backup(request: Request, body: RestoreIn) -> dict[str, str]:
    """Verify and atomically restore a local SQLite backup (local mode only)."""
    db_path = _require_local_mode(request)
    bdir = _backups_dir(db_path)

    if not _BACKUP_NAME_RE.match(body.filename) or "/" in body.filename or "\\" in body.filename:
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="Invalid backup filename.",
        )

    candidate = (bdir / body.filename).resolve()
    if not candidate.is_relative_to(bdir.resolve()):
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="Invalid backup path.",
        )
    if not candidate.is_file():
        raise ApiStatusError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message=f"Backup '{body.filename}' not found.",
        )

    with tempfile.TemporaryDirectory() as td:
        tmp_copy = Path(td) / "verify.db"
        shutil.copy2(candidate, tmp_copy)

        conn = sqlite3.connect(str(tmp_copy))
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ApiStatusError(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    code="VALIDATION_ERROR",
                    message="Backup failed SQLite integrity_check.",
                )
            alembic_row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
            if not alembic_row:
                raise ApiStatusError(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    code="VALIDATION_ERROR",
                    message="Backup is missing alembic_version metadata.",
                )
        except sqlite3.DatabaseError as exc:
            raise ApiStatusError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="VALIDATION_ERROR",
                message=f"Invalid SQLite backup: {exc}",
            ) from exc
        finally:
            conn.close()

        # Safety backup of current DB, dispose pool, swap atomically
        safety = bdir / f"purvai-pre-restore-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.db"
        _sqlite_backup(db_path, safety)

        engine = request.app.state.engine
        engine.dispose()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{db_path}{suffix}")
            sidecar.unlink(missing_ok=True)
        os.replace(tmp_copy, db_path)

        if not run_quick_check(engine):
            raise ApiStatusError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="INTERNAL_ERROR",
                message="Restored database failed quick_check.",
            )

    return {"restored": body.filename, "status": "ok"}


@router.delete("/data")
async def clear_all_data(request: Request, body: ClearDataIn) -> dict[str, bool]:
    """Delete the current household and all cascaded records after explicit confirmation."""
    if body.confirm != "DELETE":
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message='Confirmation body must be {"confirm": "DELETE"}.',
        )

    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        session.delete(household)
        session.commit()

    return {"deleted": True}
