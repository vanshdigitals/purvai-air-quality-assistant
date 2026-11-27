"""Configuration and secret handling tests."""

import tempfile
from pathlib import Path

import pytest
from app.config import REPO_ROOT, Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_database_path_resolves_relative_to_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(purvai_mode="local", database_path="data/custom.db")
    assert settings.resolved_database_path == (REPO_ROOT / "data" / "custom.db").resolve()


def test_default_database_paths_by_mode() -> None:
    local_settings = Settings(purvai_mode="local", database_path=None)
    demo_settings = Settings(purvai_mode="demo", database_path=None)
    assert local_settings.resolved_database_path == (REPO_ROOT / "data" / "purvai.db").resolve()
    assert (
        demo_settings.resolved_database_path
        == (Path(tempfile.gettempdir()) / "purvai.db").resolve()
    )


def test_app_starts_without_api_keys_and_masks_secrets(tmp_path: Path) -> None:
    secret_val = "super-secret-api-token-value"
    settings = Settings(
        purvai_mode="local",
        database_path=str(tmp_path / "cfg.db"),
        data_gov_in_api_key=None,
        gemini_api_key=secret_val,  # type: ignore[arg-type]
        groq_api_key=None,
    )
    assert secret_val not in repr(settings)
    assert secret_val not in str(settings)

    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert secret_val not in resp.text
