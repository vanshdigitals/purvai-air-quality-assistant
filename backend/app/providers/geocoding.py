"""Open-Meteo Geocoding proxy client with 24-hour in-memory cache."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import REPO_ROOT
from app.providers.base import ProviderError

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
GEOCODE_CACHE_TTL = timedelta(hours=24)
FIXTURES_DIR = REPO_ROOT / "backend" / "tests" / "fixtures"


class GeocodingResult(BaseModel):
    """Single geocoding search result returned by /api/v1/locations/search."""

    model_config = ConfigDict(frozen=True)

    label: str
    lat: float
    lon: float
    city: str | None
    admin1: str | None
    admin2: str | None
    nearest_station_km: float | None = None


@dataclass(frozen=True)
class _CacheEntry:
    cached_at: datetime
    results: list[GeocodingResult]


def parse_geocoding_payload(payload: dict[str, Any]) -> list[GeocodingResult]:
    """Parse Open-Meteo Geocoding API results into Purvai location candidates."""
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return []

    parsed: list[GeocodingResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        lat = item.get("latitude")
        lon = item.get("longitude")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(lat, int | float) or not isinstance(lon, int | float):
            continue
        country_code = item.get("country_code")
        if isinstance(country_code, str) and country_code.strip().upper() != "IN":
            continue

        city = name.strip()
        admin1 = (
            item["admin1"].strip()
            if isinstance(item.get("admin1"), str) and item["admin1"].strip()
            else None
        )
        admin2 = (
            item["admin2"].strip()
            if isinstance(item.get("admin2"), str) and item["admin2"].strip()
            else None
        )
        label = f"{city}, {admin1}" if admin1 and admin1.casefold() != city.casefold() else city
        parsed.append(
            GeocodingResult(
                label=label[:60],
                lat=round(float(lat), 4),
                lon=round(float(lon), 4),
                city=city,
                admin1=admin1,
                admin2=admin2,
            )
        )
    return parsed


def load_fake_geocoding_results(
    query: str, fixtures_dir: Path | None = None
) -> list[GeocodingResult]:
    """Load deterministic geocoding fixture results when PURVAI_FAKE_PROVIDERS is enabled."""
    path = (fixtures_dir or FIXTURES_DIR) / "geocoding_noida.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    all_results = parse_geocoding_payload(payload)
    needle = query.strip().casefold()
    matched = [
        item
        for item in all_results
        if needle in item.label.casefold()
        or (item.city and needle in item.city.casefold())
        or (item.admin1 and needle in item.admin1.casefold())
        or (item.admin2 and needle in item.admin2.casefold())
    ]
    return matched


async def search_locations(
    query: str,
    *,
    cache: dict[str, _CacheEntry],
    now: datetime | None = None,
    fake_providers: bool = False,
    client: httpx.AsyncClient | None = None,
) -> list[GeocodingResult]:
    """Search Indian locations via Open-Meteo Geocoding with 24 h in-memory cache."""
    current_time = now or datetime.now(UTC)
    cache_key = query.strip().casefold()

    entry = cache.get(cache_key)
    if entry is not None and (current_time - entry.cached_at) <= GEOCODE_CACHE_TTL:
        return list(entry.results)

    if fake_providers:
        results = load_fake_geocoding_results(query)
        cache[cache_key] = _CacheEntry(cached_at=current_time, results=results)
        return list(results)

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        try:
            response = await http_client.get(
                GEOCODING_URL,
                params={
                    "name": query.strip(),
                    "count": 8,
                    "language": "en",
                    "countryCode": "IN",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Geocoding provider request failed") from exc

        if not isinstance(payload, dict):
            raise ProviderError("Geocoding provider returned unexpected payload")

        results = parse_geocoding_payload(payload)
    finally:
        if owns_client:
            await http_client.aclose()

    cache[cache_key] = _CacheEntry(cached_at=current_time, results=results)
    return list(results)
