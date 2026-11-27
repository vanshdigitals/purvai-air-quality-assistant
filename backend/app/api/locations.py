"""Location geocoding search proxy endpoint."""

from fastapi import APIRouter, Query, Request, status
from sqlmodel import Session

from app.api.errors import ApiStatusError
from app.aqi.pipeline import get_nearest_cached_cpcb_km, utc_now
from app.providers.base import ProviderError
from app.providers.geocoding import GeocodingResult, search_locations

router = APIRouter()


@router.get("/locations/search", response_model=list[GeocodingResult])
async def search_indian_locations(
    request: Request,
    q: str = Query(..., min_length=2, max_length=60),
) -> list[GeocodingResult]:
    """Search Indian locations via Open-Meteo Geocoding with 24 h cache and 30/min rate limit."""
    locations_limiter = getattr(request.app.state, "locations_limiter", None)
    if locations_limiter is not None:
        locations_limiter._check_request_limit(request, search_indian_locations, False)

    settings = request.app.state.settings
    engine = request.app.state.engine
    cache = request.app.state.geocode_cache
    now = utc_now()

    try:
        results = await search_locations(
            q,
            cache=cache,
            now=now,
            fake_providers=settings.purvai_fake_providers,
        )
    except ProviderError as exc:
        raise ApiStatusError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="PROVIDER_UNAVAILABLE",
            message="Location search is temporarily unavailable. Enter coordinates manually.",
        ) from exc

    with Session(engine) as session:
        enriched: list[GeocodingResult] = []
        for item in results:
            nearest_km = get_nearest_cached_cpcb_km(session, item.lat, item.lon, now=now)
            enriched.append(
                GeocodingResult(
                    label=item.label,
                    lat=item.lat,
                    lon=item.lon,
                    city=item.city,
                    admin1=item.admin1,
                    admin2=item.admin2,
                    nearest_station_km=nearest_km,
                )
            )
        return enriched
