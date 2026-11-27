"""Home Air ACH calculator and deterministic indoor tips endpoints."""

from typing import Literal, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request, status
from sqlmodel import Session

from app.ai.context import build_ai_context
from app.ai.gateway import generate_indoor_advice
from app.ai.schemas.v1.models import IndoorAdvice
from app.api.errors import ApiStatusError
from app.aqi.pipeline import (
    AirForecastResponse,
    get_air_forecast,
    get_air_quality,
    parse_utc_iso,
    resolve_household_context,
    utc_now,
)
from app.db.models import SettingsRecord
from app.providers.base import ProviderError
from app.rules.catalogue import Category
from app.rules.home_air import (
    HomeAirCalcRequest,
    HomeAirCalcResponse,
    HomeAirTip,
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
    cpcb_breaker = getattr(request.app.state, "cpcb_breaker", None)

    with Session(engine) as session:
        try:
            air = await get_air_quality(
                session,
                settings=settings,
                lat=lat,
                lon=lon,
                household_header=household_header,
                cpcb_breaker=cpcb_breaker,
                prefer_cache=True,
            )
            level: Category = air.category  # type: ignore[assignment]
        except ProviderError as exc:
            raise ApiStatusError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="PROVIDER_UNAVAILABLE",
                message="Air quality data is temporarily unavailable.",
            ) from exc

        ventilation_hour: str | None = None
        forecast_resp: AirForecastResponse | None = None
        try:
            forecast_resp = await get_air_forecast(
                session,
                settings=settings,
                lat=lat,
                lon=lon,
                hours=12,
            )
            daytime = [
                h
                for h in forecast_resp.hours
                if (8, 0)
                <= (
                    (dt := parse_utc_iso(h.time).astimezone(IST_ZONE)).hour,
                    dt.minute,
                )
                <= (20, 0)
            ]
            if daytime:
                best = min(daytime, key=lambda h: h.aqi)
                ventilation_hour = best.time
        except ProviderError:
            ventilation_hour = None

        rules_res = get_home_air_tips(level, ventilation_hour=ventilation_hour)
        household, member_kinds, primary_loc = resolve_household_context(
            session,
            mode=settings.purvai_mode,
            household_header=household_header,
        )
        ai_enabled = True
        if household is not None:
            s_row = session.get(SettingsRecord, household.id)
            if s_row is not None:
                ai_enabled = bool(s_row.ai_enabled)

        has_ai_key = bool(
            settings.purvai_fake_providers or settings.gemini_api_key or settings.groq_api_key
        )
        if not (ai_enabled and has_ai_key):
            return rules_res

        context = build_ai_context(
            air=air,
            forecast=forecast_resp,
            member_kinds=member_kinds,
            city=primary_loc.city if primary_loc is not None else None,
            now_utc=utc_now(),
        )
        allowed_ids = {tip.tip_id for tip in rules_res.tips}
        gw = await generate_indoor_advice(
            settings=settings,
            context=context,
            allowed_tip_ids=allowed_ids,
            ventilation_hour=ventilation_hour,
            ai_enabled=True,
        )
        if gw.generated_by not in ("gemini", "groq"):
            return HomeAirTipsResponse(
                level=rules_res.level,
                generated_by=cast(
                    Literal["rules", "gemini", "groq", "template"],
                    gw.generated_by,
                ),
                tips=rules_res.tips,
                ventilation_hour=rules_res.ventilation_hour,
            )

        advice = cast(IndoorAdvice, gw.data)
        worded_map = {t.tip_id: t.text for t in advice.tips}
        merged_tips = [
            HomeAirTip(
                tip_id=t.tip_id,
                text=worded_map[t.tip_id] if t.tip_id in worded_map else t.text,
                tag="ai_wording" if t.tip_id in worded_map else "rule",
            )
            for t in rules_res.tips
        ]
        return HomeAirTipsResponse(
            level=rules_res.level,
            generated_by=gw.generated_by,
            tips=merged_tips,
            ventilation_hour=rules_res.ventilation_hour,
        )
