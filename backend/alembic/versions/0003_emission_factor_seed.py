"""Seed ITF-2023 emission factors (Phase 5).

Revision ID: 0003_emission_factor_seed
Revises: 0002_location_admin
Create Date: 2026-11-27 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0003_emission_factor_seed"
down_revision = "0002_location_admin"
branch_labels = None
depends_on = None

# ITF/OECD Life-Cycle Assessment of Passenger Transport - India (2023).
# g CO2e per passenger-km (lifecycle) — exactly 11 ITF-2023 modes (docs/DATABASE.md).
_FACTORS = [
    ("itf_car_petrol", "car_petrol", 162.0, "lifecycle", "ITF-2023"),
    ("itf_scooter", "scooter", 74.0, "lifecycle", "ITF-2023"),
    ("itf_motorcycle", "motorcycle", 65.0, "lifecycle", "ITF-2023"),
    ("itf_auto_cng", "auto_cng", 75.0, "lifecycle", "ITF-2023"),
    ("itf_auto_diesel", "auto_diesel", 104.0, "lifecycle", "ITF-2023"),
    ("itf_bus_diesel", "bus_diesel", 28.0, "lifecycle", "ITF-2023"),
    ("itf_bus_diesel_ac", "bus_diesel_ac", 46.0, "lifecycle", "ITF-2023"),
    ("itf_bus_cng", "bus_cng", 31.0, "lifecycle", "ITF-2023"),
    ("itf_metro", "metro", 24.0, "lifecycle", "ITF-2023"),
    ("itf_walk", "walk", 0.0, "lifecycle", "ITF-2023"),
    ("itf_cycle", "cycle", 0.0, "lifecycle", "ITF-2023"),
]


def upgrade() -> None:
    """Insert 11 ITF-2023 emission factor rows idempotently."""
    conn = op.get_bind()
    for ef_id, mode, g_co2e, basis, version in _FACTORS:
        conn.execute(
            sa.text(
                "INSERT OR IGNORE INTO emission_factor"
                " (id, mode, g_co2e_per_pkm, basis, source, version)"
                " VALUES (:id, :mode, :g, :basis, :source, :version)"
            ),
            {
                "id": ef_id,
                "mode": mode,
                "g": g_co2e,
                "basis": basis,
                "source": "ITF/OECD",
                "version": version,
            },
        )


def downgrade() -> None:
    """Remove ITF-2023 seed rows."""
    conn = op.get_bind()
    for ef_id, *_ in _FACTORS:
        conn.execute(
            sa.text("DELETE FROM emission_factor WHERE id = :id"),
            {"id": ef_id},
        )
