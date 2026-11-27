"""API v1 router and unknown /api/v1 fallback."""

from fastapi import APIRouter, HTTPException, status

from app.api.health import router as health_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)


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
