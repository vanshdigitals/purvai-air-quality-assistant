"""ITF-2023 emission factor lookup and commute-mode mapping."""

from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import EmissionFactor

VERSION = "ITF-2023"

# Map UI/settings commute_mode enum values onto the 11 ITF-2023 table modes.
COMMUTE_MODE_MAP: dict[str, str] = {
    "car": "car_petrol",
    "bus": "bus_diesel",
    "auto": "auto_cng",
    "none": "walk",
}


def resolve_factor_mode(mode: str) -> str:
    """Map a commute_mode alias onto its canonical ITF-2023 mode."""
    return COMMUTE_MODE_MAP.get(mode, mode)


def get_factor(session: Session, mode: str) -> EmissionFactor | None:
    """Return the ITF-2023 emission factor row for *mode*, or None."""
    canonical = resolve_factor_mode(mode)
    return session.exec(
        select(EmissionFactor).where(
            EmissionFactor.mode == canonical,
            EmissionFactor.version == VERSION,
        )
    ).first()


def get_all_factors(session: Session) -> list[EmissionFactor]:
    """Return all ITF-2023 emission factor rows ordered by g_co2e_per_pkm."""
    return list(
        session.exec(
            select(EmissionFactor)
            .where(EmissionFactor.version == VERSION)
            .order_by(EmissionFactor.g_co2e_per_pkm)  # type: ignore[arg-type]
        ).all()
    )
