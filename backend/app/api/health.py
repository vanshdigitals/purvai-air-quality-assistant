"""Health check endpoint."""

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db.engine import get_schema_revision, run_quick_check
from app.db.models import utc_now_iso

router = APIRouter()


class DatabaseHealth(BaseModel):
    """Database section of /health response."""

    status: str
    storage: str
    schema_revision: str | None


class HealthResponse(BaseModel):
    """Response model for GET /api/v1/health."""

    status: str
    app: str
    version: str
    mode: str
    ai_available: bool
    database: DatabaseHealth
    time: str


@router.get("/health", response_model=HealthResponse)
async def get_health(request: Request) -> JSONResponse:
    """Return liveness, runtime mode, and SQLite integrity check status."""
    settings = request.app.state.settings
    engine = request.app.state.engine

    db_ok = bool(getattr(request.app.state, "db_healthy", False)) and run_quick_check(engine)
    schema_rev = get_schema_revision(engine)
    storage = "persistent" if settings.purvai_mode == "local" else "temporary"
    ai_available = bool(settings.gemini_api_key or settings.groq_api_key)

    body = HealthResponse(
        status="ok" if db_ok else "degraded",
        app="purvai",
        version="0.1.0",
        mode=settings.purvai_mode,
        ai_available=ai_available,
        database=DatabaseHealth(
            status="ok" if db_ok else "error",
            storage=storage,
            schema_revision=schema_rev,
        ),
        time=utc_now_iso(),
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body.model_dump(),
    )
