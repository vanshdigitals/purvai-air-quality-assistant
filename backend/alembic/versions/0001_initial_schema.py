"""Initial Purvai database schema (13 tables).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all 13 documented Purvai tables, constraints, and indexes."""
    op.create_table(
        "household",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=True),
        sa.CheckConstraint("mode IN ('local', 'demo')", name="ck_household_mode"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_household_expires_at", "household", ["expires_at"], unique=False)

    op.create_table(
        "data_source",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("licence", sa.Text(), nullable=False),
        sa.Column("attribution_text", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.CheckConstraint("id IN ('cpcb', 'open_meteo')", name="ck_data_source_id"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "emission_factor",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("g_co2e_per_pkm", sa.Float(), nullable=False),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.CheckConstraint("g_co2e_per_pkm >= 0", name="ck_emission_factor_value"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mode", "version", name="uq_emission_factor_mode_version"),
    )

    op.create_table(
        "member",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('child_u12', 'adult_65p', 'heart_lung', 'outdoor_worker', 'adult')",
            name="ck_member_kind",
        ),
        sa.CheckConstraint("count >= 0", name="ck_member_count"),
        sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "kind", name="uq_member_household_kind"),
    )

    op.create_table(
        "location",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.CheckConstraint("lat >= -90.0 AND lat <= 90.0", name="ck_location_lat"),
        sa.CheckConstraint("lon >= -180.0 AND lon <= 180.0", name="ck_location_lon"),
        sa.CheckConstraint("is_primary IN (0, 1)", name="ck_location_is_primary"),
        sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_location_primary_per_household",
        "location",
        ["household_id"],
        unique=True,
        sqlite_where=sa.text("is_primary = 1"),
    )

    op.create_table(
        "settings",
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("theme", sa.Text(), nullable=False),
        sa.Column("commute_mode", sa.Text(), nullable=False),
        sa.Column("ai_enabled", sa.Boolean(), nullable=False),
        sa.Column("save_chat", sa.Boolean(), nullable=False),
        sa.Column("reduce_motion", sa.Boolean(), nullable=False),
        sa.CheckConstraint("theme IN ('light', 'dark', 'system')", name="ck_settings_theme"),
        sa.CheckConstraint(
            "commute_mode IN ('car_petrol', 'scooter', 'motorcycle', 'auto_cng', "
            "'auto_diesel', 'bus_diesel', 'bus_diesel_ac', 'bus_cng', 'metro', 'walk', 'cycle')",
            name="ck_settings_commute_mode",
        ),
        sa.CheckConstraint("ai_enabled IN (0, 1)", name="ck_settings_ai_enabled"),
        sa.CheckConstraint("save_chat IN (0, 1)", name="ck_settings_save_chat"),
        sa.CheckConstraint("reduce_motion IN (0, 1)", name="ck_settings_reduce_motion"),
        sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("household_id"),
    )

    op.create_table(
        "aqi_observation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("station_id", sa.Text(), nullable=True),
        sa.Column("lat_r", sa.Float(), nullable=False),
        sa.Column("lon_r", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source_label", sa.Text(), nullable=False),
        sa.Column("pollutants", sa.JSON(), nullable=False),
        sa.Column("aqi", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.Text(), nullable=False),
        sa.CheckConstraint("lat_r >= -90.0 AND lat_r <= 90.0", name="ck_aqi_obs_lat"),
        sa.CheckConstraint("lon_r >= -180.0 AND lon_r <= 180.0", name="ck_aqi_obs_lon"),
        sa.CheckConstraint("kind IN ('current', 'forecast')", name="ck_aqi_obs_kind"),
        sa.CheckConstraint(
            "source_label IN ('Measured', 'Modelled', 'Estimated')",
            name="ck_aqi_obs_source_label",
        ),
        sa.CheckConstraint(
            "aqi IS NULL OR (aqi >= 0 AND aqi <= 500)",
            name="ck_aqi_obs_aqi_range",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "lat_r",
            "lon_r",
            "observed_at",
            "kind",
            name="uq_aqi_obs_key",
        ),
    )
    op.create_index(
        "ix_aqi_obs_coords_time",
        "aqi_observation",
        ["lat_r", "lon_r", "observed_at"],
        unique=False,
    )

    op.create_table(
        "daily_plan",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("plan_date", sa.Text(), nullable=False),
        sa.Column("verdict_level", sa.Text(), nullable=False),
        sa.Column("aqi_observation_id", sa.Integer(), nullable=True),
        sa.Column("generated_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "verdict_level IN ('good', 'satisfactory', 'moderate', 'poor', 'very_poor', 'severe')",
            name="ck_daily_plan_verdict_level",
        ),
        sa.CheckConstraint(
            "generated_by IN ('gemini', 'groq', 'template')",
            name="ck_daily_plan_generated_by",
        ),
        sa.ForeignKeyConstraint(
            ["aqi_observation_id"], ["aqi_observation.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "plan_date", name="uq_daily_plan_household_date"),
    )

    op.create_table(
        "plan_item",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("action_id", sa.Text(), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "period IN ('morning', 'afternoon', 'evening', 'night')",
            name="ck_plan_item_period",
        ),
        sa.CheckConstraint("tag IN ('rule', 'ai_wording')", name="ck_plan_item_tag"),
        sa.ForeignKeyConstraint(["plan_id"], ["daily_plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "conversation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "message",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("text", sa.String(length=600), nullable=False),
        sa.Column("generated_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
        sa.CheckConstraint(
            "generated_by IN ('user', 'gemini', 'groq', 'template')",
            name="ck_message_generated_by",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=True),
        sa.Column("replaced_mode", sa.Text(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("hours", sa.Float(), nullable=True),
        sa.Column("factor_id", sa.Text(), nullable=True),
        sa.Column("co2_saved_g", sa.Float(), nullable=True),
        sa.Column("occurred_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "distance_km IS NULL OR (distance_km >= 0 AND distance_km <= 500)",
            name="ck_activity_log_distance",
        ),
        sa.CheckConstraint(
            "hours IS NULL OR (hours >= 0 AND hours <= 24)",
            name="ck_activity_log_hours",
        ),
        sa.ForeignKeyConstraint(["factor_id"], ["emission_factor.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activity_log_household_occurred",
        "activity_log",
        ["household_id", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "report",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.CheckConstraint("format IN ('pdf', 'csv', 'json')", name="ck_report_format"),
        sa.CheckConstraint("days IN (1, 7)", name="ck_report_days"),
        sa.CheckConstraint("byte_size >= 0", name="ck_report_byte_size"),
        sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop all 13 tables in reverse dependency order."""
    op.drop_table("report")
    op.drop_index("ix_activity_log_household_occurred", table_name="activity_log")
    op.drop_table("activity_log")
    op.drop_table("message")
    op.drop_table("conversation")
    op.drop_table("plan_item")
    op.drop_table("daily_plan")
    op.drop_index("ix_aqi_obs_coords_time", table_name="aqi_observation")
    op.drop_table("aqi_observation")
    op.drop_table("settings")
    op.drop_index("uq_location_primary_per_household", table_name="location")
    op.drop_table("location")
    op.drop_table("member")
    op.drop_table("emission_factor")
    op.drop_table("data_source")
    op.drop_index("ix_household_expires_at", table_name="household")
    op.drop_table("household")
