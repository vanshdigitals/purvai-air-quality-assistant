"""Open-Meteo Air Quality (CAMS) client and parser."""

from datetime import UTC, datetime
from typing import Any

import httpx

from app.aqi.breakpoints import PollutantId
from app.aqi.normalise import OPEN_METEO_POLLUTANT_MAP, normalise_open_meteo_value
from app.providers.base import OpenMeteoReading, ProviderError

OPEN_METEO_AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_CURRENT_VARS = "pm2_5,pm10,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide,ozone"


def parse_open_meteo_payload(payload: dict[str, Any]) -> OpenMeteoReading:
    """Parse Open-Meteo Air Quality JSON into normalised canonical units."""
    current = payload.get("current")
    if not isinstance(current, dict):
        raise ProviderError("Open-Meteo payload missing current block")

    raw_time = current.get("time")
    if not isinstance(raw_time, str) or not raw_time.strip():
        raise ProviderError("Open-Meteo payload missing current.time")

    try:
        dt = datetime.fromisoformat(raw_time.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
    except ValueError as exc:
        raise ProviderError("Open-Meteo payload has invalid current.time") from exc

    pollutants: dict[PollutantId, float] = {}
    for om_key, canonical_key in OPEN_METEO_POLLUTANT_MAP.items():
        raw_val = current.get(om_key)
        if isinstance(raw_val, int | float):
            normalised = normalise_open_meteo_value(canonical_key, float(raw_val))
            if normalised is not None:
                pollutants[canonical_key] = normalised

    lat = payload.get("latitude")
    lon = payload.get("longitude")
    return OpenMeteoReading(
        lat=float(lat) if isinstance(lat, int | float) else 0.0,
        lon=float(lon) if isinstance(lon, int | float) else 0.0,
        observed_at=dt,
        pollutants=pollutants,
    )


async def fetch_open_meteo_current(
    lat: float,
    lon: float,
    *,
    client: httpx.AsyncClient | None = None,
) -> OpenMeteoReading:
    """Fetch current modelled air quality from Open-Meteo (10 s timeout)."""
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0)

    try:
        try:
            response = await http_client.get(
                OPEN_METEO_AIR_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": OPEN_METEO_CURRENT_VARS,
                    "timezone": "UTC",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Open-Meteo request failed") from exc

        if not isinstance(payload, dict):
            raise ProviderError("Open-Meteo returned unexpected payload")
        return parse_open_meteo_payload(payload)
    finally:
        if owns_client:
            await http_client.aclose()
