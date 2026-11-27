"""Health endpoint tests."""

import pytest
from fastapi.testclient import TestClient


def test_health_local_mode(local_client: TestClient) -> None:
    response = local_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "purvai"
    assert body["version"] == "0.1.0"
    assert body["mode"] == "local"
    assert body["ai_available"] is False
    assert body["database"] == {
        "status": "ok",
        "storage": "persistent",
        "schema_revision": "0003_emission_factor_seed",
    }
    assert isinstance(body["time"], str) and body["time"].endswith("Z")
    assert ".db" not in response.text
    assert "SECRET" not in response.text.upper()


def test_health_demo_mode(demo_client: TestClient) -> None:
    response = demo_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "demo"
    assert body["database"]["storage"] == "temporary"
    assert body["database"]["schema_revision"] == "0003_emission_factor_seed"


def test_health_degraded_when_db_check_fails(
    local_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.health.run_quick_check", lambda _engine: False)
    response = local_client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["status"] == "error"
    assert ".db" not in response.text
