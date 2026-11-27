"""Open-Meteo Air Quality (CAMS) client, parser, and test-fixture loader."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.aqi.breakpoints import PollutantId
from app.aqi.normalise import OPEN_METEO_POLLUTANT_MAP, normalise_open_meteo_value
from app.config import REPO_ROOT
from app.providers.base import OpenMeteoReading, ProviderError

OPEN_METEO_AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_CURRENT_VARS = "pm2_5,pm10,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide,ozone"
FIXTURES_DIR = REPO_ROOT / "backend" / "tests" / "fixtures"


@dataclass(frozen=True)
class OpenMeteoHourlyPoint:
    """Single hourly forecast entry from Open-Meteo CAMS."""

    time: datetime
    pollutants: dict[PollutantId, float]


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
        dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
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


def parse_open_meteo_hourly(payload: dict[str, Any]) -> list[OpenMeteoHourlyPoint]:
    """Parse Open-Meteo Air Quality hourly forecast arrays into canonical units."""
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ProviderError("Open-Meteo payload missing hourly block")

    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        raise ProviderError("Open-Meteo hourly block missing time list")

    points: list[OpenMeteoHourlyPoint] = []
    for idx, raw_time in enumerate(times):
        if not isinstance(raw_time, str) or not raw_time.strip():
            continue
        try:
            dt = datetime.fromisoformat(raw_time.strip().replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
        except ValueError:
            continue

        pollutants: dict[PollutantId, float] = {}
        for om_key, canonical_key in OPEN_METEO_POLLUTANT_MAP.items():
            series = hourly.get(om_key)
            if isinstance(series, list) and idx < len(series):
                val = series[idx]
                if isinstance(val, int | float):
                    normalised = normalise_open_meteo_value(canonical_key, float(val))
                    if normalised is not None:
                        pollutants[canonical_key] = normalised

        points.append(OpenMeteoHourlyPoint(time=dt, pollutants=pollutants))

    if not points:
        raise ProviderError("Open-Meteo hourly block had no valid timestamps")
    return points


def load_fake_open_meteo_current(
    lat: float,
    lon: float,
    *,
    now: datetime | None = None,
    fixtures_dir: Path | None = None,
) -> OpenMeteoReading:
    """Load current Open-Meteo fixture with timestamp anchored to now - 20 min."""
    path = (fixtures_dir or FIXTURES_DIR) / "open_meteo_noida.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    reading = parse_open_meteo_payload(payload)
    current_time = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    return OpenMeteoReading(
        lat=lat,
        lon=lon,
        observed_at=current_time - timedelta(minutes=20),
        pollutants=reading.pollutants,
    )


def load_fake_open_meteo_forecast(
    *,
    now: datetime | None = None,
    fixtures_dir: Path | None = None,
) -> list[OpenMeteoHourlyPoint]:
    """Load 48-hour forecast fixture anchored starting 24 hours before the current UTC hour."""
    path = (fixtures_dir or FIXTURES_DIR) / "open_meteo_forecast_noida.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_points = parse_open_meteo_hourly(payload)
    base_hour = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=24
    )
    return [
        OpenMeteoHourlyPoint(
            time=base_hour + timedelta(hours=idx),
            pollutants=pt.pollutants,
        )
        for idx, pt in enumerate(raw_points)
    ]


async def fetch_open_meteo_current(
    lat: float,
    lon: float,
    *,
    fake_providers: bool = False,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> OpenMeteoReading:
    """Fetch current modelled air quality from Open-Meteo (10 s timeout)."""
    if fake_providers:
        return load_fake_open_meteo_current(lat, lon, now=now)

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


async def fetch_open_meteo_forecast(
    lat: float,
    lon: float,
    *,
    fake_providers: bool = False,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[OpenMeteoHourlyPoint]:
    """Fetch 48-hour modelled air quality forecast from Open-Meteo (10 s timeout)."""
    if fake_providers:
        return load_fake_open_meteo_forecast(now=now)

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0)

    try:
        try:
            response = await http_client.get(
                OPEN_METEO_AIR_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": OPEN_METEO_CURRENT_VARS,
                    "forecast_days": 2,
                    "timezone": "UTC",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Open-Meteo forecast request failed") from exc

        if not isinstance(payload, dict):
            raise ProviderError("Open-Meteo forecast returned unexpected payload")
        return parse_open_meteo_hourly(payload)
    finally:
        if owns_client:
            await http_client.aclose()
