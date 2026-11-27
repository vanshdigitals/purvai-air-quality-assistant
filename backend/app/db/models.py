"""SQLModel definitions matching docs/DATABASE.md."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, Column, ForeignKey, Index, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utc_now_iso() -> str:
    """Return current UTC timestamp formatted as ISO 8601 text."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_uuid4() -> str:
    """Return a new UUIDv4 string."""
    return str(uuid.uuid4())


class Household(SQLModel, table=True):
    """Household workspace record."""

    __tablename__ = "household"
    __table_args__ = (
        CheckConstraint("mode IN ('local', 'demo')", name="ck_household_mode"),
        Index("ix_household_expires_at", "expires_at"),
    )

    id: str = Field(default_factory=new_uuid4, primary_key=True)
    mode: str = Field(nullable=False)
    created_at: str = Field(default_factory=utc_now_iso, nullable=False)
    updated_at: str = Field(default_factory=utc_now_iso, nullable=False)
    expires_at: str | None = Field(default=None, nullable=True)


class Member(SQLModel, table=True):
    """Household member group counts."""

    __tablename__ = "member"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('child_u12', 'adult_65p', 'heart_lung', 'outdoor_worker', 'adult')",
            name="ck_member_kind",
        ),
        CheckConstraint("count >= 0", name="ck_member_count"),
        UniqueConstraint("household_id", "kind", name="uq_member_household_kind"),
    )

    id: int | None = Field(default=None, primary_key=True)
    household_id: str = Field(
        sa_column=Column(
            ForeignKey("household.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    kind: str = Field(nullable=False)
    count: int = Field(nullable=False)


class Location(SQLModel, table=True):
    """Saved household locations."""

    __tablename__ = "location"
    __table_args__ = (
        CheckConstraint("lat >= -90.0 AND lat <= 90.0", name="ck_location_lat"),
        CheckConstraint("lon >= -180.0 AND lon <= 180.0", name="ck_location_lon"),
        CheckConstraint("is_primary IN (0, 1)", name="ck_location_is_primary"),
        Index(
            "uq_location_primary_per_household",
            "household_id",
            unique=True,
            sqlite_where=text("is_primary = 1"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    household_id: str = Field(
        sa_column=Column(
            ForeignKey("household.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    label: str = Field(max_length=60, nullable=False)
    lat: float = Field(nullable=False)
    lon: float = Field(nullable=False)
    city: str | None = Field(default=None, max_length=120, nullable=True)
    admin1: str | None = Field(default=None, max_length=120, nullable=True)
    admin2: str | None = Field(default=None, max_length=120, nullable=True)
    is_primary: bool = Field(default=False, nullable=False)


class SettingsRecord(SQLModel, table=True):
    """Household UI and privacy preferences."""

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("theme IN ('light', 'dark', 'system')", name="ck_settings_theme"),
        CheckConstraint(
            "commute_mode IN ('car_petrol', 'scooter', 'motorcycle', 'auto_cng', 'auto_diesel', "
            "'bus_diesel', 'bus_diesel_ac', 'bus_cng', 'metro', 'walk', 'cycle', "
            "'bus', 'car', 'auto', 'none')",
            name="ck_settings_commute_mode",
        ),
        CheckConstraint("ai_enabled IN (0, 1)", name="ck_settings_ai_enabled"),
        CheckConstraint("save_chat IN (0, 1)", name="ck_settings_save_chat"),
        CheckConstraint("reduce_motion IN (0, 1)", name="ck_settings_reduce_motion"),
    )

    household_id: str = Field(
        sa_column=Column(
            ForeignKey("household.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    theme: str = Field(default="system", nullable=False)
    commute_mode: str = Field(default="metro", nullable=False)
    ai_enabled: bool = Field(default=True, nullable=False)
    save_chat: bool = Field(default=False, nullable=False)
    reduce_motion: bool = Field(default=False, nullable=False)


class DataSource(SQLModel, table=True):
    """Official or modelled air-quality data provider attribution."""

    __tablename__ = "data_source"
    __table_args__ = (CheckConstraint("id IN ('cpcb', 'open_meteo')", name="ck_data_source_id"),)

    id: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    licence: str = Field(nullable=False)
    attribution_text: str = Field(nullable=False)
    url: str = Field(nullable=False)


class AqiObservation(SQLModel, table=True):
    """Cached AQI observation or forecast."""

    __tablename__ = "aqi_observation"
    __table_args__ = (
        CheckConstraint("lat_r >= -90.0 AND lat_r <= 90.0", name="ck_aqi_obs_lat"),
        CheckConstraint("lon_r >= -180.0 AND lon_r <= 180.0", name="ck_aqi_obs_lon"),
        CheckConstraint("kind IN ('current', 'forecast')", name="ck_aqi_obs_kind"),
        CheckConstraint(
            "source_label IN ('Measured', 'Modelled', 'Estimated')",
            name="ck_aqi_obs_source_label",
        ),
        CheckConstraint(
            "aqi IS NULL OR (aqi >= 0 AND aqi <= 500)",
            name="ck_aqi_obs_aqi_range",
        ),
        UniqueConstraint(
            "source_id",
            "lat_r",
            "lon_r",
            "observed_at",
            "kind",
            name="uq_aqi_obs_key",
        ),
        Index("ix_aqi_obs_coords_time", "lat_r", "lon_r", "observed_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    source_id: str = Field(
        sa_column=Column(
            ForeignKey("data_source.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    station_id: str | None = Field(default=None, nullable=True)
    lat_r: float = Field(nullable=False)
    lon_r: float = Field(nullable=False)
    observed_at: str = Field(nullable=False)
    kind: str = Field(nullable=False)
    source_label: str = Field(nullable=False)
    pollutants: dict[str, object] = Field(sa_column=Column(JSON, nullable=False))
    aqi: int | None = Field(default=None, nullable=True)
    fetched_at: str = Field(default_factory=utc_now_iso, nullable=False)


class DailyPlan(SQLModel, table=True):
    """Daily household action plan."""

    __tablename__ = "daily_plan"
    __table_args__ = (
        CheckConstraint(
            "verdict_level IN ('good', 'satisfactory', 'moderate', 'poor', 'very_poor', 'severe')",
            name="ck_daily_plan_verdict_level",
        ),
        CheckConstraint(
            "generated_by IN ('rules', 'gemini', 'groq', 'template')",
            name="ck_daily_plan_generated_by",
        ),
        UniqueConstraint("household_id", "plan_date", name="uq_daily_plan_household_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    household_id: str = Field(
        sa_column=Column(
            ForeignKey("household.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    plan_date: str = Field(nullable=False)
    verdict_level: str = Field(nullable=False)
    aqi_observation_id: int | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("aqi_observation.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    generated_by: str = Field(nullable=False)
    created_at: str = Field(default_factory=utc_now_iso, nullable=False)


class PlanItem(SQLModel, table=True):
    """Individual period item within a daily plan."""

    __tablename__ = "plan_item"
    __table_args__ = (
        CheckConstraint(
            "period IN ('morning', 'afternoon', 'evening', 'night')",
            name="ck_plan_item_period",
        ),
        CheckConstraint("tag IN ('rule', 'ai_wording')", name="ck_plan_item_tag"),
    )

    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(
        sa_column=Column(
            ForeignKey("daily_plan.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    period: str = Field(nullable=False)
    action_id: str = Field(nullable=False)
    text: str = Field(max_length=200, nullable=False)
    tag: str = Field(nullable=False)


class Conversation(SQLModel, table=True):
    """Optional Ask Purvai conversation thread."""

    __tablename__ = "conversation"

    id: int | None = Field(default=None, primary_key=True)
    household_id: str = Field(
        sa_column=Column(
            ForeignKey("household.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    started_at: str = Field(default_factory=utc_now_iso, nullable=False)


class Message(SQLModel, table=True):
    """Chat message belonging to a conversation."""

    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
        CheckConstraint(
            "generated_by IN ('user', 'gemini', 'groq', 'template')",
            name="ck_message_generated_by",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(
        sa_column=Column(
            ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    role: str = Field(nullable=False)
    text: str = Field(max_length=600, nullable=False)
    generated_by: str = Field(nullable=False)
    created_at: str = Field(default_factory=utc_now_iso, nullable=False)


class EmissionFactor(SQLModel, table=True):
    """Lifecycle transport CO2 emission factors (seeded in Phase 5 after A-02)."""

    __tablename__ = "emission_factor"
    __table_args__ = (
        CheckConstraint("g_co2e_per_pkm >= 0", name="ck_emission_factor_value"),
        UniqueConstraint("mode", "version", name="uq_emission_factor_mode_version"),
    )

    id: str = Field(primary_key=True)
    mode: str = Field(nullable=False)
    g_co2e_per_pkm: float = Field(nullable=False)
    basis: str = Field(nullable=False)
    source: str = Field(nullable=False)
    version: str = Field(nullable=False)


class ActivityLog(SQLModel, table=True):
    """Logged household commute and exposure activities."""

    __tablename__ = "activity_log"
    __table_args__ = (
        CheckConstraint(
            "distance_km IS NULL OR (distance_km >= 0 AND distance_km <= 500)",
            name="ck_activity_log_distance",
        ),
        CheckConstraint(
            "hours IS NULL OR (hours >= 0 AND hours <= 24)",
            name="ck_activity_log_hours",
        ),
        Index("ix_activity_log_household_occurred", "household_id", "occurred_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    household_id: str = Field(
        sa_column=Column(
            ForeignKey("household.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    kind: str = Field(nullable=False)
    mode: str | None = Field(default=None, nullable=True)
    replaced_mode: str | None = Field(default=None, nullable=True)
    distance_km: float | None = Field(default=None, nullable=True)
    hours: float | None = Field(default=None, nullable=True)
    factor_id: str | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("emission_factor.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    co2_saved_g: float | None = Field(default=None, nullable=True)
    occurred_at: str = Field(default_factory=utc_now_iso, nullable=False)


class Report(SQLModel, table=True):
    """Generated report export metadata."""

    __tablename__ = "report"
    __table_args__ = (
        CheckConstraint("format IN ('pdf', 'csv', 'json')", name="ck_report_format"),
        CheckConstraint("days IN (1, 7)", name="ck_report_days"),
        CheckConstraint("byte_size >= 0", name="ck_report_byte_size"),
    )

    id: int | None = Field(default=None, primary_key=True)
    household_id: str = Field(
        sa_column=Column(
            ForeignKey("household.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    format: str = Field(nullable=False)
    days: int = Field(nullable=False)
    created_at: str = Field(default_factory=utc_now_iso, nullable=False)
    byte_size: int = Field(nullable=False)
