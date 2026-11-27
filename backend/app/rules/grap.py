"""GRAP manual configuration loader."""

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import REPO_ROOT

logger = logging.getLogger("purvai")


class GrapConfig(BaseModel):
    """Schema of config/grap.json."""

    model_config = ConfigDict(frozen=True)

    region: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    order_date: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    cities: list[str] = Field(min_length=1)


class GrapInfo(BaseModel):
    """Public GRAP banner metadata returned in /api/v1/air."""

    model_config = ConfigDict(frozen=True)

    stage: str
    order_date: str
    source_url: str


def load_grap_config(config_path: Path | None = None) -> GrapConfig | None:
    """Load and validate config/grap.json; log an error and return None if invalid."""
    path = config_path or (REPO_ROOT / "config" / "grap.json")
    if not path.is_file():
        logger.error(json.dumps({"event": "grap_config_missing"}))
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return GrapConfig.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        logger.error(json.dumps({"event": "grap_config_invalid", "error": type(exc).__name__}))
        return None


def resolve_grap(station_city: str | None, config_path: Path | None = None) -> GrapInfo | None:
    """Return GRAP metadata only when the chosen CPCB station city is in config/grap.json."""
    if not station_city or not station_city.strip():
        return None
    cfg = load_grap_config(config_path)
    if cfg is None:
        return None
    normalized_city = station_city.strip().casefold()
    allowed = {city.strip().casefold() for city in cfg.cities if city.strip()}
    if normalized_city not in allowed:
        return None
    return GrapInfo(stage=cfg.stage, order_date=cfg.order_date, source_url=cfg.source_url)
