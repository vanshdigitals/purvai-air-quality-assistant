"""AQI source selection, 30-minute SQLite cache, fallback order, and 8-day purge."""

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
from app.aqi.calculator import OverallAqiResult, compute_overall_aqi
from app.config import Settings
from app.db.models import AqiObservation, Household, Member
from app.providers.base import CpcbStationReading, ProviderError, haversine_km
from app.providers.cpcb import fetch_cpcb_stations
from app.providers.open_meteo import fetch_open_meteo_current
from app.rules.engine import Verdict, compute_verdict
from app.rules.grap import GrapInfo, resolve_grap

logger = logging.getLogger("purvai")

CACHE_TTL = timedelta(minutes=30)
FRESHNESS_LIMIT = timedelta(hours=2)
RETENTION_LIMIT = timedelta(days=8)
CPCB_MAX_DISTANCE_KM = 10.0

_missing_cpcb_key_warned = False


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


def resolve_household_members(
    session: Session,
    *,
    mode: Literal["local", "demo"],
    household_header: str | None,
) -> list[str]:
    """Load household member kinds for local or demo mode, defaulting to one adult."""
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
        return ["adult"]

    members = session.exec(select(Member).where(Member.household_id == household.id)).all()
    kinds: list[str] = []
    for member in members:
        if member.count > 0:
            kinds.extend([member.kind] * member.count)
    return kinds or ["adult"]


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
    source_label: Literal["Measured", "Modelled", "Estimated"],
    pollutants_payload: dict[str, object],
    aqi: int | None,
    fetched_at_iso: str,
) -> None:
    existing = session.exec(
        select(AqiObservation).where(
            AqiObservation.source_id == source_id,
            AqiObservation.lat_r == lat_r,
            AqiObservation.lon_r == lon_r,
            AqiObservation.observed_at == observed_at_iso,
            AqiObservation.kind == "current",
        )
    ).first()

    if existing is None:
        session.add(
            AqiObservation(
                source_id=source_id,
                station_id=station_id,
                lat_r=lat_r,
                lon_r=lon_r,
                observed_at=observed_at_iso,
                kind="current",
                source_label=source_label,
                pollutants=pollutants_payload,
                aqi=aqi,
                fetched_at=fetched_at_iso,
            )
        )
    else:
        existing.station_id = station_id
        existing.source_label = source_label
        existing.pollutants = pollutants_payload
        existing.aqi = aqi
        existing.fetched_at = fetched_at_iso


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

    if settings.data_gov_in_api_key is None:
        if not _missing_cpcb_key_warned:
            logger.warning(json.dumps({"event": "cpcb_api_key_missing"}))
            _missing_cpcb_key_warned = True
        return None

    api_key = settings.data_gov_in_api_key.get_secret_value()
    try:
        readings = await fetch_cpcb_stations(
            api_key,
            client=http_client,
            timeout_s=settings.cpcb_timeout_s,
        )
    except ProviderError as exc:
        logger.warning(json.dumps({"event": "cpcb_fetch_failed", "reason": str(exc)}))
        return None

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


async def _try_open_meteo(
    session: Session,
    *,
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
        reading = await fetch_open_meteo_current(req_lat, req_lon, client=http_client)
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

    # Also check cached CPCB stations within 10 km whose rounded coords differ from (lat_r, lon_r).
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
) -> AirQualityResponse:
    """Execute the full AQI pipeline: CPCB -> Open-Meteo -> SQLite cache -> verdict."""
    now = utc_now()

    candidate = await _try_cpcb(
        session,
        settings=settings,
        req_lat=lat,
        req_lon=lon,
        now=now,
        http_client=http_client,
    )
    if candidate is None:
        candidate = await _try_open_meteo(
            session,
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

    member_kinds = resolve_household_members(
        session,
        mode=settings.purvai_mode,
        household_header=household_header,
    )
    verdict = compute_verdict(candidate.aqi_result.category, member_kinds)

    if candidate.source_id == "cpcb":
        source = SourceMeta(
            provider="CPCB",
            station=candidate.station_name,
            distance_km=candidate.distance_km,
        )
        attribution = ["CPCB", "data.gov.in"]
        grap = resolve_grap(candidate.city, config_path=grap_path)
    else:
        source = SourceMeta(
            provider="Open-Meteo (CAMS)",
            station=None,
            distance_km=None,
        )
        attribution = ["Open-Meteo", "CAMS"]
        grap = None

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
