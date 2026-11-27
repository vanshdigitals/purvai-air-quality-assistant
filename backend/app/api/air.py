"""Air quality endpoint router."""

from datetime import timedelta

from fastapi import APIRouter, Query, Request, status
from sqlmodel import Session

from app.api.errors import ApiStatusError
from app.aqi.pipeline import AirQualityResponse, get_air_quality, purge_old_observations, utc_now
from app.providers.base import ProviderError

router = APIRouter()

INDIA_LAT_MIN = 6.0
INDIA_LAT_MAX = 38.0
INDIA_LON_MIN = 68.0
INDIA_LON_MAX = 98.0


@router.get("/air", response_model=AirQualityResponse)
async def get_air(
    request: Request,
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
) -> AirQualityResponse:
    """Return current AQI, source attribution, GRAP banner, and household verdict."""
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
        now = utc_now()
        last_purge = getattr(request.app.state, "last_purge_at", None)
        if last_purge is None or (now - last_purge) >= timedelta(days=1):
            purge_old_observations(session, now)
            request.app.state.last_purge_at = now

        try:
            return await get_air_quality(
                session,
                settings=settings,
                lat=lat,
                lon=lon,
                household_header=household_header,
            )
        except ProviderError as exc:
            raise ApiStatusError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="PROVIDER_UNAVAILABLE",
                message="Air quality data is temporarily unavailable. Please try again shortly.",
            ) from exc
