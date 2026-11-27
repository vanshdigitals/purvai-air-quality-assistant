"""Shared test fixtures for Purvai backend tests."""

from pathlib import Path

import pytest
from app.config import Settings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_env_from_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent root .env from leaking real API keys into automated unit tests."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in (
        "DATA_GOV_IN_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "AI_MODEL",
        "AI_PROVIDER",
        "AI_FALLBACK_PROVIDER",
        "AI_FALLBACK_MODEL",
        "AI_TIMEOUT_S",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


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
