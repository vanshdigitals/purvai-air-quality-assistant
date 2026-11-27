"""SQLite engine, PRAGMA setup, session dependency, and integrity helpers."""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event, text
from sqlmodel import Session, create_engine


def create_sqlite_engine(db_path: Path) -> Engine:
    """Create a SQLite SQLAlchemy engine with per-connection safety PRAGMAs."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

    return engine


def apply_local_db_permissions(db_path: Path) -> None:
    """Restrict database file permissions to owner read/write where supported."""
    if db_path.exists():
        try:
            os.chmod(db_path, 0o600)
        except OSError:
            pass


def run_quick_check(engine: Engine) -> bool:
    """Run SQLite PRAGMA quick_check and return True only when result is 'ok'."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA quick_check;")).scalar_one_or_none()
            return str(result).lower() == "ok"
    except Exception:
        return False


def get_schema_revision(engine: Engine) -> str | None:
    """Read current Alembic revision from alembic_version if present."""
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1;")).first()
            return str(row[0]) if row is not None else None
    except Exception:
        return None


def session_generator(engine: Engine) -> Generator[Session, None, None]:
    """Yield one SQLModel session per request."""
    with Session(engine) as session:
        yield session
