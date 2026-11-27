"""CPCB data.gov.in client and parser (resource 3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69)."""

import hashlib
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.aqi.breakpoints import PollutantId
from app.aqi.normalise import map_cpcb_pollutant, normalise_cpcb_value
from app.providers.base import CpcbStationReading, ProviderError

CPCB_RESOURCE_URL = "https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
IST_ZONE = ZoneInfo("Asia/Kolkata")
PAGE_LIMIT = 1000


def _first_present(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _parse_float(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return float(raw)
    text = str(raw).strip()
    if not text or text.upper() in {"NA", "N/A", "NULL", "NONE", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_cpcb_timestamp(raw: Any) -> datetime | None:
    """Parse CPCB local Indian timestamp into a timezone-aware UTC datetime."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or text.upper() in {"NA", "N/A"}:
        return None

    for fmt in ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            naive = datetime.strptime(text, fmt)
            return naive.replace(tzinfo=IST_ZONE).astimezone(UTC)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=IST_ZONE).astimezone(UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _station_id_for(station_name: str, city: str, lat: float, lon: float) -> str:
    raw = f"{station_name.strip().lower()}|{city.strip().lower()}|{lat:.4f}|{lon:.4f}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def parse_cpcb_records(records: list[dict[str, Any]]) -> list[CpcbStationReading]:
    """Group flat CPCB pollutant records by monitoring station."""
    grouped: dict[tuple[str, str, float, float], dict[str, Any]] = {}

    for rec in records:
        station_raw = _first_present(rec, "station", "station_name")
        city_raw = _first_present(rec, "city")
        state_raw = _first_present(rec, "state")
        lat = _parse_float(_first_present(rec, "latitude", "lat"))
        lon = _parse_float(_first_present(rec, "longitude", "lon", "lng"))
        observed_at = parse_cpcb_timestamp(_first_present(rec, "last_update", "updated_at"))
        pollutant = map_cpcb_pollutant(str(_first_present(rec, "pollutant_id", "pollutant") or ""))
        avg_val = _parse_float(_first_present(rec, "pollutant_avg", "avg_value", "avg"))
        unit_raw = _first_present(rec, "pollutant_unit", "unit")

        if (
            not isinstance(station_raw, str)
            or not station_raw.strip()
            or lat is None
            or lon is None
            or observed_at is None
            or pollutant is None
            or avg_val is None
        ):
            continue

        normalised_val = normalise_cpcb_value(
            pollutant,
            avg_val,
            str(unit_raw) if isinstance(unit_raw, str) else None,
        )
        if normalised_val is None:
            continue

        station_name = station_raw.strip()
        city = str(city_raw).strip() if isinstance(city_raw, str) else ""
        state = str(state_raw).strip() if isinstance(state_raw, str) else ""
        key = (station_name, city, round(lat, 6), round(lon, 6))

        entry = grouped.get(key)
        if entry is None:
            entry = {
                "station_name": station_name,
                "city": city,
                "state": state,
                "lat": lat,
                "lon": lon,
                "observed_at": observed_at,
                "pollutants": {},
            }
            grouped[key] = entry

        if observed_at > entry["observed_at"]:
            entry["observed_at"] = observed_at

        pollutants_map: dict[PollutantId, float] = entry["pollutants"]
        pollutants_map[pollutant] = normalised_val

    readings: list[CpcbStationReading] = []
    for entry in grouped.values():
        readings.append(
            CpcbStationReading(
                station_id=_station_id_for(
                    entry["station_name"], entry["city"], entry["lat"], entry["lon"]
                ),
                station_name=entry["station_name"],
                city=entry["city"],
                state=entry["state"],
                lat=entry["lat"],
                lon=entry["lon"],
                observed_at=entry["observed_at"],
                pollutants=dict(entry["pollutants"]),
            )
        )
    return readings


async def fetch_cpcb_stations(
    api_key: str,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int = PAGE_LIMIT,
) -> list[CpcbStationReading]:
    """Fetch and paginate all CPCB station records from data.gov.in (10 s timeout)."""
    all_records: list[dict[str, Any]] = []
    offset = 0
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0)

    try:
        while True:
            try:
                response = await http_client.get(
                    CPCB_RESOURCE_URL,
                    params={
                        "api-key": api_key,
                        "format": "json",
                        "limit": limit,
                        "offset": offset,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ProviderError("CPCB provider request failed") from exc

            if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
                raise ProviderError("CPCB provider returned unexpected payload")

            batch = [rec for rec in payload["records"] if isinstance(rec, dict)]
            all_records.extend(batch)

            total = payload.get("total")
            if not batch or len(batch) < limit:
                break
            offset += len(batch)
            if isinstance(total, int) and offset >= total:
                break
    finally:
        if owns_client:
            await http_client.aclose()

    return parse_cpcb_records(all_records)
