"""Unit conversion, pollutant key mapping, and table-precision truncation."""

import math
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from app.aqi.breakpoints import PollutantId

# CPCB data.gov.in resource 3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69 reports:
#   PM2.5, PM10, NO2, SO2, OZONE in ug/m3 (micrograms per cubic metre)
#   CO in mg/m3 (milligrams per cubic metre)
CPCB_POLLUTANT_MAP: dict[str, PollutantId] = {
    "PM2.5": "pm25",
    "PM25": "pm25",
    "PM10": "pm10",
    "NO2": "no2",
    "SO2": "so2",
    "CO": "co",
    "OZONE": "o3",
    "O3": "o3",
}

OPEN_METEO_POLLUTANT_MAP: dict[str, PollutantId] = {
    "pm2_5": "pm25",
    "pm10": "pm10",
    "nitrogen_dioxide": "no2",
    "sulphur_dioxide": "so2",
    "carbon_monoxide": "co",
    "ozone": "o3",
}


def map_cpcb_pollutant(raw_id: str | None) -> PollutantId | None:
    """Map a CPCB pollutant_id string to a canonical Purvai pollutant key."""
    if not raw_id:
        return None
    return CPCB_POLLUTANT_MAP.get(raw_id.strip().upper())


def normalise_cpcb_value(
    pollutant: PollutantId, value: float, unit: str | None = None
) -> float | None:
    """Normalise a CPCB pollutant concentration into canonical units (µg/m³; CO mg/m³)."""
    if not math.isfinite(value) or value < 0:
        return None
    if pollutant == "co" and unit is not None:
        cleaned = unit.strip().lower()
        if "ug" in cleaned or "µg" in cleaned or "μg" in cleaned:
            return value / 1000.0
    return value


def normalise_open_meteo_value(pollutant: PollutantId, value: float) -> float | None:
    """Normalise Open-Meteo current pollutant values (CO converted from µg/m³ to mg/m³)."""
    if not math.isfinite(value) or value < 0:
        return None
    if pollutant == "co":
        return value / 1000.0
    return value


def truncate_for_lookup(pollutant: PollutantId, value: float) -> float:
    """Truncate concentration to breakpoint table precision before band lookup (P2-4).

    Whole numbers for PM2.5, PM10, NO2, O3, SO2; one decimal place for CO.
    """
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid concentration {value} for {pollutant}")
    try:
        dec = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid concentration {value} for {pollutant}") from exc

    quantum = Decimal("0.1") if pollutant == "co" else Decimal("1")
    return float(dec.quantize(quantum, rounding=ROUND_DOWN))
