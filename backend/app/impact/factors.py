"""ITF-2023 emission factor lookup."""

from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import EmissionFactor

VERSION = "ITF-2023"


def get_factor(session: Session, mode: str) -> EmissionFactor | None:
    """Return the ITF-2023 emission factor row for *mode*, or None."""
    return session.exec(
        select(EmissionFactor).where(
            EmissionFactor.mode == mode,
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
