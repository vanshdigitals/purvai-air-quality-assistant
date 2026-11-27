"""Idempotent seed data for Phase 1."""

from sqlmodel import Session

from app.db.models import DataSource

DATA_SOURCES: tuple[DataSource, ...] = (
    DataSource(
        id="cpcb",
        name="CPCB via data.gov.in",
        licence="GODL-India",
        attribution_text="Measured air quality data from CPCB via data.gov.in (GODL-India).",
        url="https://data.gov.in",
    ),
    DataSource(
        id="open_meteo",
        name="Open-Meteo Air Quality (CAMS)",
        licence="CC BY 4.0",
        attribution_text=(
            "Modelled air quality and forecast data from Open-Meteo / CAMS (CC BY 4.0)."
        ),
        url="https://open-meteo.com",
    ),
)


def seed_data_sources(session: Session) -> None:
    """Idempotently upsert official data_source attribution rows."""
    for source in DATA_SOURCES:
        existing = session.get(DataSource, source.id)
        if existing is None:
            session.add(DataSource.model_validate(source))
        else:
            existing.name = source.name
            existing.licence = source.licence
            existing.attribution_text = source.attribution_text
            existing.url = source.url
    session.commit()
