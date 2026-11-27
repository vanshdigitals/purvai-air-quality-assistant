"""Household persistence and demo header scoping endpoints."""

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.api.errors import ApiStatusError
from app.aqi.pipeline import to_utc_iso, utc_now
from app.db.models import Household, Location, Member, SettingsRecord
from app.rules.catalogue import MemberKind

router = APIRouter()

INDIA_LAT_MIN = 6.0
INDIA_LAT_MAX = 38.0
INDIA_LON_MIN = 68.0
INDIA_LON_MAX = 98.0

CommuteModeIn = Literal[
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


class MemberIn(BaseModel):
    """Single household member kind count."""

    model_config = ConfigDict(extra="forbid")

    kind: MemberKind
    count: int = Field(ge=0, le=20)


class LocationIn(BaseModel):
    """Primary household location input."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=60)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    city: str | None = Field(default=None, max_length=120)
    admin1: str | None = Field(default=None, max_length=120)
    admin2: str | None = Field(default=None, max_length=120)


class SettingsIn(BaseModel):
    """Household preferences input."""

    model_config = ConfigDict(extra="forbid")

    theme: Literal["light", "dark", "system"] = "system"
    commute_mode: CommuteModeIn = "metro"
    ai_enabled: bool = True
    save_chat: bool = False
    reduce_motion: bool = False


class HouseholdPutRequest(BaseModel):
    """Body schema for PUT /api/v1/household."""

    model_config = ConfigDict(extra="forbid")

    members: list[MemberIn] = Field(min_length=1, max_length=10)
    location: LocationIn
    settings: SettingsIn

    @model_validator(mode="after")
    def _validate_members(self) -> "HouseholdPutRequest":
        kinds = [m.kind for m in self.members]
        if len(kinds) != len(set(kinds)):
            raise ValueError("Duplicate member kinds are not allowed.")
        if sum(m.count for m in self.members) < 1:
            raise ValueError("At least one household member must have count >= 1.")
        return self


class HouseholdResponse(BaseModel):
    """Response model for GET and PUT /api/v1/household."""

    model_config = ConfigDict(frozen=True)

    id: str
    mode: Literal["local", "demo"]
    updated_at: str
    members: list[MemberIn]
    location: LocationIn
    settings: SettingsIn


def purge_expired_demo_households(session: Session, now: datetime | None = None) -> int:
    """Delete expired demo households (cascading to child rows)."""
    current = now or utc_now()
    now_iso = to_utc_iso(current)
    result = session.exec(
        delete(Household).where(
            col(Household.mode) == "demo",
            col(Household.expires_at).is_not(None),
            col(Household.expires_at) < now_iso,
        )
    )
    session.commit()
    return int(result.rowcount or 0)


def parse_demo_household_header(request: Request) -> str:
    """Require and validate UUIDv4 X-Purvai-Household header in demo mode."""
    raw = request.headers.get("X-Purvai-Household")
    if not raw or not raw.strip():
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="HOUSEHOLD_HEADER_REQUIRED",
            message="X-Purvai-Household UUIDv4 header is required in demo mode.",
        )
    candidate = raw.strip()
    try:
        parsed = uuid.UUID(candidate, version=4)
    except ValueError as exc:
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="HOUSEHOLD_HEADER_REQUIRED",
            message="X-Purvai-Household must be a valid UUIDv4.",
        ) from exc
    if parsed.version != 4 or str(parsed) != candidate.lower():
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="HOUSEHOLD_HEADER_REQUIRED",
            message="X-Purvai-Household must be a canonical UUIDv4.",
        )
    return str(parsed)


def _find_household(
    session: Session,
    *,
    mode: Literal["local", "demo"],
    demo_id: str | None,
    now_iso: str,
) -> Household | None:
    if mode == "local":
        return session.exec(select(Household).where(Household.mode == "local")).first()
    if demo_id is None:
        return None
    hh = session.exec(
        select(Household).where(
            Household.id == demo_id,
            Household.mode == "demo",
        )
    ).first()
    if hh is not None and hh.expires_at is not None and hh.expires_at < now_iso:
        return None
    return hh


def _build_household_response(session: Session, household: Household) -> HouseholdResponse:
    members_rows = session.exec(select(Member).where(Member.household_id == household.id)).all()
    primary_loc = session.exec(
        select(Location).where(
            Location.household_id == household.id,
            Location.is_primary.is_(True),  # type: ignore[attr-defined]
        )
    ).first()
    settings_row = session.get(SettingsRecord, household.id)

    if primary_loc is None or settings_row is None:
        raise ApiStatusError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="HOUSEHOLD_NOT_FOUND",
            message="Household profile has not been initialized.",
        )

    return HouseholdResponse(
        id=household.id,
        mode="local" if household.mode == "local" else "demo",
        updated_at=household.updated_at,
        members=[MemberIn(kind=m.kind, count=m.count) for m in members_rows],
        location=LocationIn(
            label=primary_loc.label,
            lat=primary_loc.lat,
            lon=primary_loc.lon,
            city=primary_loc.city,
            admin1=primary_loc.admin1,
            admin2=primary_loc.admin2,
        ),
        settings=SettingsIn(
            theme=settings_row.theme,
            commute_mode=settings_row.commute_mode,
            ai_enabled=settings_row.ai_enabled,
            save_chat=settings_row.save_chat,
            reduce_motion=settings_row.reduce_motion,
        ),
    )


def resolve_existing_household(
    request: Request, session: Session
) -> tuple[Household, list[str], Location]:
    """Resolve initialized household, members, and primary location or raise 409."""
    settings = request.app.state.settings
    now = utc_now()
    now_iso = to_utc_iso(now)

    demo_id = parse_demo_household_header(request) if settings.purvai_mode == "demo" else None
    household = _find_household(
        session,
        mode=settings.purvai_mode,
        demo_id=demo_id,
        now_iso=now_iso,
    )
    if household is None:
        raise ApiStatusError(
            status_code=status.HTTP_409_CONFLICT,
            code="HOUSEHOLD_REQUIRED",
            message="Complete onboarding to create a household before building a plan.",
        )

    primary_loc = session.exec(
        select(Location).where(
            Location.household_id == household.id,
            Location.is_primary.is_(True),  # type: ignore[attr-defined]
        )
    ).first()
    if primary_loc is None:
        raise ApiStatusError(
            status_code=status.HTTP_409_CONFLICT,
            code="HOUSEHOLD_REQUIRED",
            message="A primary location is required before building a plan.",
        )

    members = session.exec(select(Member).where(Member.household_id == household.id)).all()
    kinds: list[str] = []
    for member in members:
        if member.count > 0:
            kinds.extend([member.kind] * member.count)
    return household, kinds or ["adult"], primary_loc


@router.get("/household", response_model=HouseholdResponse)
async def get_household(request: Request) -> HouseholdResponse:
    """Return the active household profile, or 404 before onboarding."""
    settings = request.app.state.settings
    engine = request.app.state.engine
    demo_id = parse_demo_household_header(request) if settings.purvai_mode == "demo" else None
    now_iso = to_utc_iso(utc_now())

    with Session(engine) as session:
        household = _find_household(
            session,
            mode=settings.purvai_mode,
            demo_id=demo_id,
            now_iso=now_iso,
        )
        if household is None:
            raise ApiStatusError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="HOUSEHOLD_NOT_FOUND",
                message="No household profile found.",
            )
        return _build_household_response(session, household)


@router.put("/household", response_model=HouseholdResponse)
async def put_household(request: Request, body: HouseholdPutRequest) -> HouseholdResponse:
    """Create or replace household members, settings, and primary location."""
    if not (
        INDIA_LAT_MIN <= body.location.lat <= INDIA_LAT_MAX
        and INDIA_LON_MIN <= body.location.lon <= INDIA_LON_MAX
    ):
        raise ApiStatusError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="UNSUPPORTED_REGION",
            message="Purvai currently supports locations in India.",
        )

    settings = request.app.state.settings
    engine = request.app.state.engine
    demo_id = parse_demo_household_header(request) if settings.purvai_mode == "demo" else None
    now = utc_now()
    now_iso = to_utc_iso(now)
    expires_iso = to_utc_iso(now + timedelta(hours=24)) if settings.purvai_mode == "demo" else None

    with Session(engine) as session:
        household = _find_household(
            session,
            mode=settings.purvai_mode,
            demo_id=demo_id,
            now_iso=now_iso,
        )

        if household is None:
            new_id = demo_id if demo_id is not None else str(uuid.uuid4())
            household = Household(
                id=new_id,
                mode=settings.purvai_mode,
                created_at=now_iso,
                updated_at=now_iso,
                expires_at=expires_iso,
            )
            session.add(household)
            session.flush()
        else:
            household.updated_at = now_iso
            household.expires_at = expires_iso

        session.exec(delete(Member).where(Member.household_id == household.id))  # type: ignore[arg-type]
        for member_in in body.members:
            session.add(
                Member(
                    household_id=household.id,
                    kind=member_in.kind,
                    count=member_in.count,
                )
            )

        existing_locations = session.exec(
            select(Location).where(
                Location.household_id == household.id,
                Location.is_primary.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        for old_loc in existing_locations:
            old_loc.is_primary = False
        session.flush()

        session.add(
            Location(
                household_id=household.id,
                label=body.location.label.strip(),
                lat=round(body.location.lat, 4),
                lon=round(body.location.lon, 4),
                city=body.location.city.strip() if body.location.city else None,
                admin1=body.location.admin1.strip() if body.location.admin1 else None,
                admin2=body.location.admin2.strip() if body.location.admin2 else None,
                is_primary=True,
            )
        )

        existing_settings = session.get(SettingsRecord, household.id)
        if existing_settings is None:
            session.add(
                SettingsRecord(
                    household_id=household.id,
                    theme=body.settings.theme,
                    commute_mode=body.settings.commute_mode,
                    ai_enabled=body.settings.ai_enabled,
                    save_chat=body.settings.save_chat,
                    reduce_motion=body.settings.reduce_motion,
                )
            )
        else:
            existing_settings.theme = body.settings.theme
            existing_settings.commute_mode = body.settings.commute_mode
            existing_settings.ai_enabled = body.settings.ai_enabled
            existing_settings.save_chat = body.settings.save_chat
            existing_settings.reduce_motion = body.settings.reduce_motion

        session.commit()
        session.refresh(household)
        return _build_household_response(session, household)
