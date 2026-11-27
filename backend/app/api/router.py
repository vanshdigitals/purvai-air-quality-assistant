"""API v1 router and unknown /api/v1 fallback."""

from fastapi import APIRouter, HTTPException, status

from app.api.air import router as air_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.home_air import router as home_air_router
from app.api.household import router as household_router
from app.api.impact import router as impact_router
from app.api.locations import router as locations_router
from app.api.plan import router as plan_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(air_router)
api_v1_router.include_router(household_router)
api_v1_router.include_router(locations_router)
api_v1_router.include_router(plan_router)
api_v1_router.include_router(home_air_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(impact_router)


@api_v1_router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def api_not_found(full_path: str) -> None:
    """Ensure unknown /api/v1/* paths always return JSON 404, never SPA HTML."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Endpoint /api/v1/{full_path} not found.",
    )
