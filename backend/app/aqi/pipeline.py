"""AQI source selection, forecast caching, 30-minute SQLite cache, fallback, and purge."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

import httpx
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.aqi.breakpoints import POLLUTANT_TIE_ORDER, PollutantId
from app.aqi.calculator import OverallAqiResult, category_for_aqi, compute_overall_aqi
from app.config import Settings
from app.db.models import AqiObservation, Household, Location, Member
from app.providers.base import CpcbStationReading, ProviderError, haversine_km
from app.providers.cpcb import fetch_cpcb_stations
from app.providers.open_meteo import (
    OpenMeteoHourlyPoint,
    fetch_open_meteo_current,
    fetch_open_meteo_forecast,
)
from app.rules.catalogue import Category
from app.rules.engine import Verdict, compute_verdict
from app.rules.grap import GrapInfo, resolve_grap

logger = logging.getLogger("purvai")

CACHE_TTL = timedelta(minutes=30)
FRESHNESS_LIMIT = timedelta(hours=2)
RETENTION_LIMIT = timedelta(days=8)
CPCB_MAX_DISTANCE_KM = 10.0
CPCB_BREAKER_COOLDOWN = timedelta(minutes=15)

_missing_cpcb_key_warned = False


class CpcbCircuitBreaker:
    """In-memory circuit breaker skipping failing CPCB refreshes for 15 minutes."""

    def __init__(self, cooldown: timedelta = CPCB_BREAKER_COOLDOWN) -> None:
        self.cooldown = cooldown
        self._opened_at: datetime | None = None

    def state(self, now: datetime | None = None) -> Literal["closed", "open", "half_open"]:
        """Return current breaker state: closed, open (<15 min), or half_open (>=15 min)."""
        if self._opened_at is None:
            return "closed"
        current = now or utc_now()
        if (current - self._opened_at) < self.cooldown:
            return "open"
        return "half_open"

    def should_skip(self, now: datetime | None = None) -> bool:
        """Return True while breaker is open and CPCB requests must be skipped."""
        return self.state(now) == "open"

    def record_success(self) -> None:
        """Close the circuit breaker after a successful CPCB refresh."""
        self._opened_at = None

    def record_failure(self, now: datetime | None = None) -> None:
        """Open (or re-open) the circuit breaker for cooldown duration."""
        self._opened_at = now or utc_now()


def utc_now() -> datetime:
    """Return current UTC datetime without microseconds."""
    return datetime.now(UTC).replace(microsecond=0)


def to_utc_iso(dt: datetime) -> str:
    """Format an aware datetime as ISO 8601 UTC string."""
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc_iso(raw: str) -> datetime:
    """Parse stored ISO 8601 UTC string into aware datetime."""
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


class SourceMeta(BaseModel):
    """Source attribution metadata for /api/v1/air."""

    model_config = ConfigDict(frozen=True)

    provider: str
    station: str | None
    distance_km: float | None


class PollutantReadingOut(BaseModel):
    """Individual pollutant output block."""

    model_config = ConfigDict(frozen=True)

    value: float
    unit: str
    sub_index: int


class AirQualityResponse(BaseModel):
    """Full GET /api/v1/air response payload matching docs/API.md."""

    model_config = ConfigDict(frozen=True)

    aqi: int
    aqi_is_floor: bool
    category: str
    scale: Literal["CPCB_NAQI"] = "CPCB_NAQI"
    source_label: Literal["Measured", "Modelled", "Estimated"]
    source: SourceMeta
    observed_at: str
    age_minutes: int
    stale: bool
    indicative: bool = True
    served_from_cache: bool
    dominant_pollutant: str
    pollutants: dict[str, PollutantReadingOut]
    verdict: Verdict
    grap: GrapInfo | None
    attribution: list[str]


class ForecastHourOut(BaseModel):
    """Single hourly point in /api/v1/air/forecast."""

    model_config = ConfigDict(frozen=True)

    time: str
    aqi: int
    aqi_is_floor: bool
    category: Category
    dominant_pollutant: str


class ForecastLowestOut(BaseModel):
    """Cleanest forecast hour summary."""

    model_config = ConfigDict(frozen=True)

    time: str
    aqi: int
    category: Category


class AirForecastResponse(BaseModel):
    """Full GET /api/v1/air/forecast response payload."""

    model_config = ConfigDict(frozen=True)

    scale: Literal["CPCB_NAQI"] = "CPCB_NAQI"
    source_label: Literal["Modelled"] = "Modelled"
    indicative: bool = True
    attribution: list[str]
    generated_at: str
    hours: list[ForecastHourOut]
    lowest: ForecastLowestOut


@dataclass(frozen=True)
class _CandidateObservation:
    source_id: Literal["cpcb", "open_meteo"]
    source_label: Literal["Measured", "Modelled", "Estimated"]
    station_name: str | None
    city: str | None
    distance_km: float | None
    observed_at: datetime
    aqi_result: OverallAqiResult
    served_from_cache: bool


def purge_old_observations(session: Session, now: datetime | None = None) -> int:
    """Delete cached aqi_observation rows older than 8 days."""
    current = now or utc_now()
    cutoff_iso = to_utc_iso(current - RETENTION_LIMIT)
    result = session.exec(
        delete(AqiObservation).where(AqiObservation.fetched_at < cutoff_iso)  # type: ignore[arg-type]
    )
    session.commit()
    return int(result.rowcount or 0)


def resolve_household_context(
    session: Session,
    *,
    mode: Literal["local", "demo"],
    household_header: str | None,
) -> tuple[Household | None, list[str], Location | None]:
    """Load household, member kinds, and primary location for local or demo mode."""
    household: Household | None = None
    if mode == "local":
        household = session.exec(select(Household).where(Household.mode == "local")).first()
    elif household_header and household_header.strip():
        household = session.exec(
            select(Household).where(
                Household.id == household_header.strip(),
                Household.mode == "demo",
            )
        ).first()

    if household is None:
        return None, ["adult"], None

    members = session.exec(select(Member).where(Member.household_id == household.id)).all()
    kinds: list[str] = []
    for member in members:
        if member.count > 0:
            kinds.extend([member.kind] * member.count)

    primary_location = session.exec(
        select(Location).where(
            Location.household_id == household.id,
            Location.is_primary.is_(True),  # type: ignore[attr-defined]
        )
    ).first()

    return household, kinds or ["adult"], primary_location


def resolve_household_members(
    session: Session,
    *,
    mode: Literal["local", "demo"],
    household_header: str | None,
) -> list[str]:
    """Load household member kinds for local or demo mode, defaulting to one adult."""
    _, kinds, _ = resolve_household_context(session, mode=mode, household_header=household_header)
    return kinds


def _extract_pollutants_and_meta(
    stored: dict[str, object],
) -> tuple[dict[PollutantId, float], str | None, str | None, float | None, float | None]:
    raw_values = stored.get("values") if isinstance(stored.get("values"), dict) else stored
    values: dict[PollutantId, float] = {}
    if isinstance(raw_values, dict):
        for p_key in POLLUTANT_TIE_ORDER:
            val = raw_values.get(p_key)
            if isinstance(val, int | float):
                values[p_key] = float(val)

    station_name = (
        str(stored["station_name"]) if isinstance(stored.get("station_name"), str) else None
    )
    city = str(stored["city"]) if isinstance(stored.get("city"), str) else None
    raw_lat = stored.get("lat")
    raw_lon = stored.get("lon")
    lat = float(raw_lat) if isinstance(raw_lat, int | float) else None
    lon = float(raw_lon) if isinstance(raw_lon, int | float) else None
    return values, station_name, city, lat, lon


def _upsert_observation(
    session: Session,
    *,
    source_id: Literal["cpcb", "open_meteo"],
    station_id: str | None,
    lat_r: float,
    lon_r: float,
    observed_at_iso: str,
    kind: Literal["current", "forecast"],
    source_label: Literal["Measured", "Modelled", "Estimated"],
    pollutants_payload: dict[str, object],
    aqi: int | None,
    fetched_at_iso: str,
) -> AqiObservation:
    existing = session.exec(
        select(AqiObservation).where(
            AqiObservation.source_id == source_id,
            AqiObservation.lat_r == lat_r,
            AqiObservation.lon_r == lon_r,
            AqiObservation.observed_at == observed_at_iso,
            AqiObservation.kind == kind,
        )
    ).first()

    if existing is None:
        obs = AqiObservation(
            source_id=source_id,
            station_id=station_id,
            lat_r=lat_r,
            lon_r=lon_r,
            observed_at=observed_at_iso,
            kind=kind,
            source_label=source_label,
            pollutants=pollutants_payload,
            aqi=aqi,
            fetched_at=fetched_at_iso,
        )
        session.add(obs)
        return obs

    existing.station_id = station_id
    existing.source_label = source_label
    existing.pollutants = pollutants_payload
    existing.aqi = aqi
    existing.fetched_at = fetched_at_iso
    return existing


def get_nearest_cached_cpcb_km(
    session: Session,
    lat: float,
    lon: float,
    now: datetime | None = None,
) -> float | None:
    """Return nearest CPCB station distance in km if the CPCB cache is warm (< 30 min)."""
    current = now or utc_now()
    latest_fetched_raw = session.exec(
        select(func.max(AqiObservation.fetched_at)).where(
            AqiObservation.source_id == "cpcb",
            AqiObservation.kind == "current",
        )
    ).one()
    if not isinstance(latest_fetched_raw, str):
        return None
    if (current - parse_utc_iso(latest_fetched_raw)) > CACHE_TTL:
        return None

    rows = list(
        session.exec(
            select(AqiObservation).where(
                AqiObservation.source_id == "cpcb",
                AqiObservation.kind == "current",
            )
        ).all()
    )
    if not rows:
        return None

    best_km: float | None = None
    for row in rows:
        _, _, _, s_lat, s_lon = _extract_pollutants_and_meta(row.pollutants)
        station_lat = s_lat if s_lat is not None else row.lat_r
        station_lon = s_lon if s_lon is not None else row.lon_r
        dist = haversine_km(lat, lon, station_lat, station_lon)
        if best_km is None or dist < best_km:
            best_km = dist
    return round(best_km, 1) if best_km is not None else None


def _select_best_cpcb_from_rows(
    rows: list[AqiObservation],
    *,
    req_lat: float,
    req_lon: float,
    now: datetime,
    require_fresh: bool,
    served_from_cache: bool,
) -> _CandidateObservation | None:
    best: tuple[float, _CandidateObservation] | None = None

    for row in rows:
        values, station_name, city, s_lat, s_lon = _extract_pollutants_and_meta(row.pollutants)
        station_lat = s_lat if s_lat is not None else row.lat_r
        station_lon = s_lon if s_lon is not None else row.lon_r
        dist = haversine_km(req_lat, req_lon, station_lat, station_lon)
        if dist > CPCB_MAX_DISTANCE_KM:
            continue

        obs_dt = parse_utc_iso(row.observed_at)
        if require_fresh and (now - obs_dt) > FRESHNESS_LIMIT:
            continue

        aqi_res = compute_overall_aqi(values)
        if aqi_res is None:
            continue

        source_label: Literal["Measured", "Estimated"] = (
            "Measured" if aqi_res.meets_three_pollutant_rule else "Estimated"
        )
        candidate = _CandidateObservation(
            source_id="cpcb",
            source_label=source_label,
            station_name=station_name or row.station_id,
            city=city,
            distance_km=round(dist, 1),
            observed_at=obs_dt,
            aqi_result=aqi_res,
            served_from_cache=served_from_cache,
        )
        if best is None or dist < best[0]:
            best = (dist, candidate)

    return best[1] if best is not None else None


def _select_best_cpcb_from_readings(
    readings: list[CpcbStationReading],
    *,
    req_lat: float,
    req_lon: float,
    now: datetime,
) -> _CandidateObservation | None:
    best: tuple[float, _CandidateObservation] | None = None

    for reading in readings:
        dist = haversine_km(req_lat, req_lon, reading.lat, reading.lon)
        if dist > CPCB_MAX_DISTANCE_KM:
            continue
        if (now - reading.observed_at) > FRESHNESS_LIMIT:
            continue
        aqi_res = compute_overall_aqi(reading.pollutants)
        if aqi_res is None:
            continue

        source_label: Literal["Measured", "Estimated"] = (
            "Measured" if aqi_res.meets_three_pollutant_rule else "Estimated"
        )
        candidate = _CandidateObservation(
            source_id="cpcb",
            source_label=source_label,
            station_name=reading.station_name,
            city=reading.city,
            distance_km=round(dist, 1),
            observed_at=reading.observed_at,
            aqi_result=aqi_res,
            served_from_cache=False,
        )
        if best is None or dist < best[0]:
            best = (dist, candidate)

    return best[1] if best is not None else None


async def _try_cpcb(
    session: Session,
    *,
    settings: Settings,
    req_lat: float,
    req_lon: float,
    now: datetime,
    http_client: httpx.AsyncClient | None,
    cpcb_breaker: CpcbCircuitBreaker | None = None,
) -> _CandidateObservation | None:
    global _missing_cpcb_key_warned

    latest_fetched_raw = session.exec(
        select(func.max(AqiObservation.fetched_at)).where(
            AqiObservation.source_id == "cpcb",
            AqiObservation.kind == "current",
        )
    ).one()

    if isinstance(latest_fetched_raw, str):
        latest_fetched = parse_utc_iso(latest_fetched_raw)
        if (now - latest_fetched) <= CACHE_TTL:
            cached_rows = list(
                session.exec(
                    select(AqiObservation).where(
                        AqiObservation.source_id == "cpcb",
                        AqiObservation.kind == "current",
                    )
                ).all()
            )
            return _select_best_cpcb_from_rows(
                cached_rows,
                req_lat=req_lat,
                req_lon=req_lon,
                now=now,
                require_fresh=True,
                served_from_cache=False,
            )

    if cpcb_breaker is not None and cpcb_breaker.should_skip(now):
        logger.debug(json.dumps({"event": "cpcb_breaker_skip"}))
        return None

    if settings.data_gov_in_api_key is None and not settings.purvai_fake_providers:
        if not _missing_cpcb_key_warned:
            logger.warning(json.dumps({"event": "cpcb_api_key_missing"}))
            _missing_cpcb_key_warned = True
        return None

    api_key = (
        settings.data_gov_in_api_key.get_secret_value()
        if settings.data_gov_in_api_key is not None
        else ""
    )
    try:
        readings = await fetch_cpcb_stations(
            api_key,
            client=http_client,
            timeout_s=settings.cpcb_timeout_s,
            fake_providers=settings.purvai_fake_providers,
            now=now,
        )
    except ProviderError as exc:
        if cpcb_breaker is not None:
            cpcb_breaker.record_failure(now)
        logger.warning(json.dumps({"event": "cpcb_fetch_failed", "reason": str(exc)}))
        return None

    if cpcb_breaker is not None:
        cpcb_breaker.record_success()

    fetched_iso = to_utc_iso(now)
    for reading in readings:
        aqi_res = compute_overall_aqi(reading.pollutants)
        label: Literal["Measured", "Estimated"] = (
            "Measured" if aqi_res and aqi_res.meets_three_pollutant_rule else "Estimated"
        )
        payload: dict[str, object] = {
            "values": dict(reading.pollutants),
            "station_name": reading.station_name,
            "city": reading.city,
            "lat": reading.lat,
            "lon": reading.lon,
        }
        _upsert_observation(
            session,
            source_id="cpcb",
            station_id=reading.station_id,
            lat_r=round(reading.lat, 2),
            lon_r=round(reading.lon, 2),
            observed_at_iso=to_utc_iso(reading.observed_at),
            kind="current",
            source_label=label,
            pollutants_payload=payload,
            aqi=aqi_res.aqi if aqi_res else None,
            fetched_at_iso=fetched_iso,
        )
    session.commit()

    return _select_best_cpcb_from_readings(
        readings,
        req_lat=req_lat,
        req_lon=req_lon,
        now=now,
    )


def _find_fresh_open_meteo_cached(
    session: Session,
    *,
    req_lat: float,
    req_lon: float,
    now: datetime,
) -> _CandidateObservation | None:
    lat_r = round(req_lat, 2)
    lon_r = round(req_lon, 2)
    cached = session.exec(
        select(AqiObservation)
        .where(
            AqiObservation.source_id == "open_meteo",
            AqiObservation.kind == "current",
            AqiObservation.lat_r == lat_r,
            AqiObservation.lon_r == lon_r,
        )
        .order_by(AqiObservation.fetched_at.desc())  # type: ignore[attr-defined]
    ).first()
    if cached is not None and (now - parse_utc_iso(cached.fetched_at)) <= CACHE_TTL:
        values, _, _, _, _ = _extract_pollutants_and_meta(cached.pollutants)
        aqi_res = compute_overall_aqi(values)
        if aqi_res is not None:
            label: Literal["Modelled", "Estimated"] = (
                "Modelled" if aqi_res.meets_three_pollutant_rule else "Estimated"
            )
            return _CandidateObservation(
                source_id="open_meteo",
                source_label=label,
                station_name=None,
                city=None,
                distance_km=None,
                observed_at=parse_utc_iso(cached.observed_at),
                aqi_result=aqi_res,
                served_from_cache=False,
            )
    return None


async def refresh_cpcb_in_background(
    session: Session,
    *,
    settings: Settings,
    cpcb_breaker: CpcbCircuitBreaker | None = None,
    http_client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> int:
    """Refresh CPCB station cache outside user request paths (never blocks callers)."""
    current = now or utc_now()
    if cpcb_breaker is not None and cpcb_breaker.should_skip(current):
        return 0
    if settings.data_gov_in_api_key is None and not settings.purvai_fake_providers:
        return 0
    api_key = (
        settings.data_gov_in_api_key.get_secret_value()
        if settings.data_gov_in_api_key is not None
        else ""
    )
    try:
        readings = await fetch_cpcb_stations(
            api_key,
            client=http_client,
            timeout_s=settings.cpcb_timeout_s,
            fake_providers=settings.purvai_fake_providers,
            now=current,
        )
    except ProviderError as exc:
        if cpcb_breaker is not None:
            cpcb_breaker.record_failure(current)
        logger.warning(json.dumps({"event": "cpcb_background_refresh_failed", "reason": str(exc)}))
        return 0
    if cpcb_breaker is not None:
        cpcb_breaker.record_success()
    fetched_iso = to_utc_iso(current)
    for reading in readings:
        aqi_res = compute_overall_aqi(reading.pollutants)
        label: Literal["Measured", "Estimated"] = (
            "Measured" if aqi_res and aqi_res.meets_three_pollutant_rule else "Estimated"
        )
        _upsert_observation(
            session,
            source_id="cpcb",
            station_id=reading.station_id,
            lat_r=round(reading.lat, 2),
            lon_r=round(reading.lon, 2),
            observed_at_iso=to_utc_iso(reading.observed_at),
            kind="current",
            source_label=label,
            pollutants_payload={
                "values": dict(reading.pollutants),
                "station_name": reading.station_name,
                "city": reading.city,
                "lat": reading.lat,
                "lon": reading.lon,
            },
            aqi=aqi_res.aqi if aqi_res else None,
            fetched_at_iso=fetched_iso,
        )
    session.commit()
    return len(readings)


async def _try_open_meteo(
    session: Session,
    *,
    settings: Settings,
    req_lat: float,
    req_lon: float,
    now: datetime,
    http_client: httpx.AsyncClient | None,
) -> _CandidateObservation | None:
    lat_r = round(req_lat, 2)
    lon_r = round(req_lon, 2)

    cached = session.exec(
        select(AqiObservation)
        .where(
            AqiObservation.source_id == "open_meteo",
            AqiObservation.kind == "current",
            AqiObservation.lat_r == lat_r,
            AqiObservation.lon_r == lon_r,
        )
        .order_by(AqiObservation.fetched_at.desc())  # type: ignore[attr-defined]
    ).first()

    if cached is not None and (now - parse_utc_iso(cached.fetched_at)) <= CACHE_TTL:
        values, _, _, _, _ = _extract_pollutants_and_meta(cached.pollutants)
        aqi_res = compute_overall_aqi(values)
        if aqi_res is not None:
            label: Literal["Modelled", "Estimated"] = (
                "Modelled" if aqi_res.meets_three_pollutant_rule else "Estimated"
            )
            return _CandidateObservation(
                source_id="open_meteo",
                source_label=label,
                station_name=None,
                city=None,
                distance_km=None,
                observed_at=parse_utc_iso(cached.observed_at),
                aqi_result=aqi_res,
                served_from_cache=False,
            )

    try:
        reading = await fetch_open_meteo_current(
            req_lat,
            req_lon,
            fake_providers=settings.purvai_fake_providers,
            now=now,
            client=http_client,
        )
    except ProviderError as exc:
        logger.warning(json.dumps({"event": "open_meteo_fetch_failed", "reason": str(exc)}))
        return None

    aqi_res = compute_overall_aqi(reading.pollutants)
    if aqi_res is None:
        return None

    source_label: Literal["Modelled", "Estimated"] = (
        "Modelled" if aqi_res.meets_three_pollutant_rule else "Estimated"
    )
    obs_iso = to_utc_iso(reading.observed_at)
    fetched_iso = to_utc_iso(now)
    _upsert_observation(
        session,
        source_id="open_meteo",
        station_id=None,
        lat_r=lat_r,
        lon_r=lon_r,
        observed_at_iso=obs_iso,
        kind="current",
        source_label=source_label,
        pollutants_payload={"values": dict(reading.pollutants)},
        aqi=aqi_res.aqi,
        fetched_at_iso=fetched_iso,
    )
    session.commit()

    return _CandidateObservation(
        source_id="open_meteo",
        source_label=source_label,
        station_name=None,
        city=None,
        distance_km=None,
        observed_at=reading.observed_at,
        aqi_result=aqi_res,
        served_from_cache=False,
    )


def _try_fallback_cache(
    session: Session,
    *,
    req_lat: float,
    req_lon: float,
    now: datetime,
) -> _CandidateObservation | None:
    lat_r = round(req_lat, 2)
    lon_r = round(req_lon, 2)

    rows = list(
        session.exec(
            select(AqiObservation)
            .where(
                AqiObservation.kind == "current",
                AqiObservation.lat_r == lat_r,
                AqiObservation.lon_r == lon_r,
                AqiObservation.aqi.is_not(None),  # type: ignore[union-attr]
            )
            .order_by(
                AqiObservation.observed_at.desc(),  # type: ignore[attr-defined]
                AqiObservation.fetched_at.desc(),  # type: ignore[attr-defined]
            )
        ).all()
    )

    for row in rows:
        values, station_name, city, s_lat, s_lon = _extract_pollutants_and_meta(row.pollutants)
        aqi_res = compute_overall_aqi(values)
        if aqi_res is None:
            continue
        dist: float | None = None
        if row.source_id == "cpcb":
            st_lat = s_lat if s_lat is not None else row.lat_r
            st_lon = s_lon if s_lon is not None else row.lon_r
            dist = round(haversine_km(req_lat, req_lon, st_lat, st_lon), 1)
            if dist > CPCB_MAX_DISTANCE_KM:
                continue
        return _CandidateObservation(
            source_id=cast(Literal["cpcb", "open_meteo"], row.source_id),
            source_label=cast(Literal["Measured", "Modelled", "Estimated"], row.source_label),
            station_name=station_name if row.source_id == "cpcb" else None,
            city=city if row.source_id == "cpcb" else None,
            distance_km=dist,
            observed_at=parse_utc_iso(row.observed_at),
            aqi_result=aqi_res,
            served_from_cache=True,
        )

    cpcb_rows = list(
        session.exec(
            select(AqiObservation)
            .where(
                AqiObservation.source_id == "cpcb",
                AqiObservation.kind == "current",
                AqiObservation.aqi.is_not(None),  # type: ignore[union-attr]
            )
            .order_by(
                AqiObservation.observed_at.desc(),  # type: ignore[attr-defined]
                AqiObservation.fetched_at.desc(),  # type: ignore[attr-defined]
            )
        ).all()
    )
    return _select_best_cpcb_from_rows(
        cpcb_rows,
        req_lat=req_lat,
        req_lon=req_lon,
        now=now,
        require_fresh=False,
        served_from_cache=True,
    )


async def get_air_quality(
    session: Session,
    *,
    settings: Settings,
    lat: float,
    lon: float,
    household_header: str | None = None,
    http_client: httpx.AsyncClient | None = None,
    grap_path: Path | None = None,
    cpcb_breaker: CpcbCircuitBreaker | None = None,
    prefer_cache: bool = False,
) -> AirQualityResponse:
    """Execute AQI pipeline: cache (when preferred) / CPCB -> Open-Meteo -> SQLite -> verdict."""
    now = utc_now()
    candidate: _CandidateObservation | None = None

    if prefer_cache:
        latest_cpcb = session.exec(
            select(func.max(AqiObservation.fetched_at)).where(
                AqiObservation.source_id == "cpcb",
                AqiObservation.kind == "current",
            )
        ).one()
        if isinstance(latest_cpcb, str) and (now - parse_utc_iso(latest_cpcb)) <= CACHE_TTL:
            cpcb_rows = list(
                session.exec(
                    select(AqiObservation).where(
                        AqiObservation.source_id == "cpcb",
                        AqiObservation.kind == "current",
                    )
                ).all()
            )
            candidate = _select_best_cpcb_from_rows(
                cpcb_rows,
                req_lat=lat,
                req_lon=lon,
                now=now,
                require_fresh=True,
                served_from_cache=False,
            )
        if candidate is None:
            candidate = _find_fresh_open_meteo_cached(
                session,
                req_lat=lat,
                req_lon=lon,
                now=now,
            )

    if candidate is None:
        candidate = await _try_cpcb(
            session,
            settings=settings,
            req_lat=lat,
            req_lon=lon,
            now=now,
            http_client=http_client,
            cpcb_breaker=cpcb_breaker,
        )
    if candidate is None:
        candidate = await _try_open_meteo(
            session,
            settings=settings,
            req_lat=lat,
            req_lon=lon,
            now=now,
            http_client=http_client,
        )
    if candidate is None:
        candidate = _try_fallback_cache(session, req_lat=lat, req_lon=lon, now=now)
    if candidate is None:
        raise ProviderError("No air quality provider or cached observation available")

    age_seconds = max(0.0, (now - candidate.observed_at).total_seconds())
    age_minutes = int(age_seconds // 60)
    stale = age_seconds > FRESHNESS_LIMIT.total_seconds()

    _, member_kinds, primary_location = resolve_household_context(
        session,
        mode=settings.purvai_mode,
        household_header=household_header,
    )
    verdict = compute_verdict(candidate.aqi_result.category, member_kinds)
    location_cities: tuple[str | None, ...] = (
        (primary_location.city, primary_location.admin2, primary_location.admin1)
        if primary_location is not None
        else ()
    )

    if candidate.source_id == "cpcb":
        source = SourceMeta(
            provider="CPCB",
            station=candidate.station_name,
            distance_km=candidate.distance_km,
        )
        attribution = ["CPCB", "data.gov.in"]
        grap = resolve_grap(
            candidate.city,
            config_path=grap_path,
            location_cities=location_cities,
        )
    else:
        source = SourceMeta(
            provider="Open-Meteo (CAMS)",
            station=None,
            distance_km=None,
        )
        attribution = ["Open-Meteo", "CAMS"]
        grap = resolve_grap(
            None,
            config_path=grap_path,
            location_cities=location_cities,
        )

    pollutants_out = {
        pid: PollutantReadingOut(
            value=sub.value,
            unit=sub.unit,
            sub_index=sub.sub_index,
        )
        for pid, sub in candidate.aqi_result.sub_indices.items()
    }

    return AirQualityResponse(
        aqi=candidate.aqi_result.aqi,
        aqi_is_floor=candidate.aqi_result.aqi_is_floor,
        category=candidate.aqi_result.category,
        scale="CPCB_NAQI",
        source_label=candidate.source_label,
        source=source,
        observed_at=to_utc_iso(candidate.observed_at),
        age_minutes=age_minutes,
        stale=stale,
        indicative=True,
        served_from_cache=candidate.served_from_cache,
        dominant_pollutant=candidate.aqi_result.dominant_pollutant,
        pollutants=pollutants_out,
        verdict=verdict,
        grap=grap,
        attribution=attribution,
    )


async def get_hourly_forecast_points(
    session: Session,
    *,
    settings: Settings,
    lat: float,
    lon: float,
    now: datetime | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[list[ForecastHourOut], int | None]:
    """Load or fetch 48-hour forecast points with 30-min SQLite caching."""
    current = now or utc_now()
    lat_r = round(lat, 2)
    lon_r = round(lon, 2)

    cached = session.exec(
        select(AqiObservation)
        .where(
            AqiObservation.source_id == "open_meteo",
            AqiObservation.kind == "forecast",
            AqiObservation.lat_r == lat_r,
            AqiObservation.lon_r == lon_r,
        )
        .order_by(AqiObservation.fetched_at.desc())  # type: ignore[attr-defined]
    ).first()

    computed_hours: list[ForecastHourOut] = []
    obs_id: int | None = None

    if cached is not None and (current - parse_utc_iso(cached.fetched_at)) <= CACHE_TTL:
        raw_hours = cached.pollutants.get("hours")
        if isinstance(raw_hours, list):
            for entry in raw_hours:
                if isinstance(entry, dict) and isinstance(entry.get("time"), str):
                    computed_hours.append(ForecastHourOut.model_validate(entry))
            obs_id = cached.id

    if not computed_hours:
        raw_points: list[OpenMeteoHourlyPoint] = await fetch_open_meteo_forecast(
            lat,
            lon,
            fake_providers=settings.purvai_fake_providers,
            now=current,
            client=http_client,
        )
        for pt in raw_points:
            aqi_res = compute_overall_aqi(pt.pollutants)
            if aqi_res is None:
                continue
            computed_hours.append(
                ForecastHourOut(
                    time=to_utc_iso(pt.time),
                    aqi=aqi_res.aqi,
                    aqi_is_floor=aqi_res.aqi_is_floor,
                    category=aqi_res.category,
                    dominant_pollutant=aqi_res.dominant_pollutant,
                )
            )
        if not computed_hours:
            raise ProviderError("Open-Meteo forecast yielded no valid AQI hours")

        payload: dict[str, object] = {"hours": [h.model_dump() for h in computed_hours]}
        stored = _upsert_observation(
            session,
            source_id="open_meteo",
            station_id=None,
            lat_r=lat_r,
            lon_r=lon_r,
            observed_at_iso=computed_hours[0].time,
            kind="forecast",
            source_label="Modelled",
            pollutants_payload=payload,
            aqi=computed_hours[0].aqi,
            fetched_at_iso=to_utc_iso(current),
        )
        session.commit()
        session.refresh(stored)
        obs_id = stored.id

    return computed_hours, obs_id


async def get_air_forecast(
    session: Session,
    *,
    settings: Settings,
    lat: float,
    lon: float,
    hours: int = 12,
    http_client: httpx.AsyncClient | None = None,
) -> AirForecastResponse:
    """Return modelled hourly CPCB AQI forecast and lowest hour summary."""
    now = utc_now()
    all_hours, _ = await get_hourly_forecast_points(
        session,
        settings=settings,
        lat=lat,
        lon=lon,
        now=now,
        http_client=http_client,
    )
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    upcoming = [h for h in all_hours if parse_utc_iso(h.time) >= current_hour][:hours]
    if not upcoming:
        upcoming = all_hours[:hours]
    if not upcoming:
        raise ProviderError("No forecast hours available")

    lowest_pt = min(upcoming, key=lambda h: h.aqi)
    return AirForecastResponse(
        scale="CPCB_NAQI",
        source_label="Modelled",
        indicative=True,
        attribution=["Open-Meteo", "CAMS"],
        generated_at=to_utc_iso(now),
        hours=upcoming,
        lowest=ForecastLowestOut(
            time=lowest_pt.time,
            aqi=lowest_pt.aqi,
            category=category_for_aqi(lowest_pt.aqi),
        ),
    )
