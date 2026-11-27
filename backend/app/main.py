"""Purvai FastAPI application factory."""

import json
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlmodel import Session

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware, configure_json_logger
from app.api.router import api_v1_router
from app.config import REPO_ROOT, Settings, get_settings
from app.db.engine import (
    apply_local_db_permissions,
    create_sqlite_engine,
    run_quick_check,
    session_generator,
)
from app.db.seed import seed_data_sources

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def run_migrations(db_path: Path) -> None:
    """Run Alembic upgrade head programmatically against the configured SQLite DB."""
    alembic_cfg = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(alembic_cfg, "head")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application instance."""
    resolved_settings = settings or get_settings()
    logger = configure_json_logger(resolved_settings.log_level)
    db_path = resolved_settings.resolved_database_path
    engine = create_sqlite_engine(db_path)

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{resolved_settings.rate_limit_per_minute}/minute"],
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            run_migrations(db_path)
            if resolved_settings.purvai_mode == "local":
                apply_local_db_permissions(db_path)
            with Session(engine) as session:
                seed_data_sources(session)
            db_ok = run_quick_check(engine)
            if not db_ok:
                logger.error(json.dumps({"event": "db_quick_check_failed"}))
            app.state.db_healthy = db_ok
        except Exception as exc:
            logger.error(json.dumps({"event": "db_startup_error", "error": type(exc).__name__}))
            app.state.db_healthy = False
        yield
        engine.dispose()

    app = FastAPI(
        title="Purvai API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.engine = engine
    app.state.limiter = limiter
    app.state.db_healthy = False

    register_exception_handlers(app)

    if resolved_settings.purvai_mode == "local":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[resolved_settings.cors_dev_origin],
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        RequestContextMiddleware,
        mode=resolved_settings.purvai_mode,
        logger=logger,
    )

    app.include_router(api_v1_router)

    dist_dir = REPO_ROOT / "frontend" / "dist"
    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint /{full_path} not found.",
            )
        if not dist_dir.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Frontend bundle not built.",
            )
        candidate = (dist_dir / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist_dir.resolve()):
            return FileResponse(candidate)
        index_file = dist_dir / "index.html"
        if not index_file.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Frontend index.html not found.",
            )
        return FileResponse(index_file)

    return app


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency yielding a SQLModel session."""
    yield from session_generator(request.app.state.engine)


app = create_app()
