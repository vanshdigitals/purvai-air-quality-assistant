"""Shared provider models, errors, and geospatial helpers."""

import math
from dataclasses import dataclass
from datetime import datetime

from app.aqi.breakpoints import PollutantId


class ProviderError(Exception):
    """Raised when an external air-quality provider fails or returns invalid data."""


@dataclass(frozen=True)
class CpcbStationReading:
    """Normalised station reading grouped from CPCB data.gov.in records."""

    station_id: str
    station_name: str
    city: str
    state: str
    lat: float
    lon: float
    observed_at: datetime
    pollutants: dict[PollutantId, float]


@dataclass(frozen=True)
class OpenMeteoReading:
    """Normalised current air-quality reading from Open-Meteo CAMS."""

    lat: float
    lon: float
    observed_at: datetime
    pollutants: dict[PollutantId, float]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in kilometres between two WGS84 coordinates."""
    earth_radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (
        math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_km * c
