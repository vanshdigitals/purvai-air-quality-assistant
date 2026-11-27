"""Home Air ACH calculator and deterministic indoor tips endpoints."""

from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request, status
from sqlmodel import Session

from app.api.errors import ApiStatusError
from app.aqi.pipeline import get_air_forecast, get_air_quality, parse_utc_iso
from app.providers.base import ProviderError
from app.rules.catalogue import Category
from app.rules.home_air import (
    HomeAirCalcRequest,
    HomeAirCalcResponse,
    HomeAirTipsResponse,
    calculate_home_air,
    get_home_air_tips,
)

router = APIRouter()

INDIA_LAT_MIN = 6.0
INDIA_LAT_MAX = 38.0
INDIA_LON_MIN = 68.0
INDIA_LON_MAX = 98.0
IST_ZONE = ZoneInfo("Asia/Kolkata")


@router.post("/home-air/calc", response_model=HomeAirCalcResponse)
async def post_home_air_calc(body: HomeAirCalcRequest) -> HomeAirCalcResponse:
    """Calculate room ACH against Purvai's target of 5 ACH."""
    return calculate_home_air(body)


@router.get("/home-air/tips", response_model=HomeAirTipsResponse)
async def get_home_air_tips_endpoint(
    request: Request,
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
) -> HomeAirTipsResponse:
    """Return deterministic indoor air tips and daytime ventilation hour."""
    if not (INDIA_LAT_MIN <= lat <= INDIA_LAT_MAX and INDIA_LON_MIN <= lon <= INDIA_LON_MAX):
        raise ApiStatusError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="UNSUPPORTED_REGION",
            message="Purvai currently supports locations in India.",
        )

    settings = request.app.state.settings
    engine = request.app.state.engine
    household_header = request.headers.get("X-Purvai-Household")

    with Session(engine) as session:
        try:
            air = await get_air_quality(
                session,
                settings=settings,
                lat=lat,
                lon=lon,
                household_header=household_header,
            )
            level: Category = air.category  # type: ignore[assignment]
        except ProviderError as exc:
            raise ApiStatusError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="PROVIDER_UNAVAILABLE",
                message="Air quality data is temporarily unavailable.",
            ) from exc

        ventilation_hour: str | None = None
        try:
            forecast = await get_air_forecast(
                session,
                settings=settings,
                lat=lat,
                lon=lon,
                hours=12,
            )
            daytime = [
                h
                for h in forecast.hours
                if 8 <= parse_utc_iso(h.time).astimezone(IST_ZONE).hour <= 20
            ]
            if daytime:
                best = min(daytime, key=lambda h: h.aqi)
                best_ist = parse_utc_iso(best.time).astimezone(IST_ZONE)
                ventilation_hour = f"{best_ist.hour:02d}:00 IST"
        except ProviderError:
            ventilation_hour = None

        return get_home_air_tips(level, ventilation_hour=ventilation_hour)
