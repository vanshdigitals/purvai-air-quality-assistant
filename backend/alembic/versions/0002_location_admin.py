"""Add city, admin1, admin2 to location and Phase 3 enum choices.

Revision ID: 0002_location_admin
Revises: 0001_initial_schema
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_location_admin"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add administrative locality fields on location and Phase 3 enum options."""
    with op.batch_alter_table("location", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("city", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("admin1", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("admin2", sa.String(length=120), nullable=True))

    with op.batch_alter_table("settings", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_settings_commute_mode", type_="check")
        batch_op.create_check_constraint(
            "ck_settings_commute_mode",
            "commute_mode IN ('car_petrol', 'scooter', 'motorcycle', 'auto_cng', "
            "'auto_diesel', 'bus_diesel', 'bus_diesel_ac', 'bus_cng', 'metro', 'walk', "
            "'cycle', 'bus', 'car', 'auto', 'none')",
        )

    with op.batch_alter_table("daily_plan", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_daily_plan_generated_by", type_="check")
        batch_op.create_check_constraint(
            "ck_daily_plan_generated_by",
            "generated_by IN ('rules', 'gemini', 'groq', 'template')",
        )


def downgrade() -> None:
    """Revert location administrative columns and Phase 3 enum additions."""
    with op.batch_alter_table("daily_plan", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_daily_plan_generated_by", type_="check")
        batch_op.create_check_constraint(
            "ck_daily_plan_generated_by",
            "generated_by IN ('gemini', 'groq', 'template')",
        )

    with op.batch_alter_table("settings", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_settings_commute_mode", type_="check")
        batch_op.create_check_constraint(
            "ck_settings_commute_mode",
            "commute_mode IN ('car_petrol', 'scooter', 'motorcycle', 'auto_cng', "
            "'auto_diesel', 'bus_diesel', 'bus_diesel_ac', 'bus_cng', 'metro', 'walk', 'cycle')",
        )

    with op.batch_alter_table("location", recreate="always") as batch_op:
        batch_op.drop_column("admin2")
        batch_op.drop_column("admin1")
        batch_op.drop_column("city")
