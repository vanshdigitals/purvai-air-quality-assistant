"""Daily Protection Plan endpoint."""

from typing import Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app.api.errors import ApiStatusError
from app.api.household import resolve_existing_household
from app.providers.base import ProviderError
from app.rules.plan import DailyPlanResponse, build_daily_plan

router = APIRouter()


class PlanRequest(BaseModel):
    """Body schema for POST /api/v1/plan."""

    model_config = ConfigDict(extra="forbid")

    day: Literal["today", "tomorrow"] = "today"
    rebuild: bool = False


@router.post("/plan", response_model=DailyPlanResponse)
async def post_plan(request: Request, body: PlanRequest) -> DailyPlanResponse:
    """Build and persist the 4-period Daily Protection Plan for the household."""
    settings = request.app.state.settings
    engine = request.app.state.engine
    household_header = request.headers.get("X-Purvai-Household")
    plan_ai_cache = getattr(request.app.state, "plan_ai_cache", None)
    cpcb_breaker = getattr(request.app.state, "cpcb_breaker", None)

    with Session(engine) as session:
        household, member_kinds, primary_loc = resolve_existing_household(request, session)
        try:
            return await build_daily_plan(
                session,
                settings=settings,
                household=household,
                member_kinds=member_kinds,
                location=primary_loc,
                day=body.day,
                rebuild=body.rebuild,
                household_header=household_header,
                plan_ai_cache=plan_ai_cache,
                cpcb_breaker=cpcb_breaker,
            )
        except ProviderError as exc:
            raise ApiStatusError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="PROVIDER_UNAVAILABLE",
                message="Air quality forecast is temporarily unavailable.",
            ) from exc
