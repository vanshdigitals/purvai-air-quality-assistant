"""Shared test fixtures for Purvai backend tests."""

from pathlib import Path

import pytest
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def local_client(tmp_path: Path) -> TestClient:
    """Create a TestClient configured for local mode with a temporary SQLite DB."""
    db_file = tmp_path / "local_test.db"
    settings = Settings(
        purvai_mode="local",
        database_path=str(db_file),
        rate_limit_per_minute=1000,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def demo_client(tmp_path: Path) -> TestClient:
    """Create a TestClient configured for demo mode with a temporary SQLite DB."""
    db_file = tmp_path / "demo_test.db"
    settings = Settings(
        purvai_mode="demo",
        database_path=str(db_file),
        rate_limit_per_minute=1000,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client
