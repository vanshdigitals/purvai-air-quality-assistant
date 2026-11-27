"""Tests for JSON export and import with dry_run (FR-14)."""

from fastapi.testclient import TestClient


def _setup_data(client: TestClient) -> None:
    resp = client.put(
        "/api/v1/household",
        json={
            "members": [{"kind": "adult", "count": 2}],
            "location": {
                "label": "Noida",
                "lat": 28.6271,
                "lon": 77.3716,
                "city": "Noida",
            },
            "settings": {
                "theme": "light",
                "commute_mode": "metro",
                "ai_enabled": False,
                "save_chat": False,
                "reduce_motion": False,
            },
        },
    )
    assert resp.status_code == 200
    act = client.post(
        "/api/v1/activities",
        json={
            "kind": "commute",
            "mode": "metro",
            "replaced_mode": "car_petrol",
            "distance_km": 12.0,
        },
    )
    assert act.status_code == 201


def test_export_dry_run_and_import_roundtrip(local_client: TestClient) -> None:
    """Export -> dry_run=true -> modify -> import replaces household and activities."""
    _setup_data(local_client)

    exp = local_client.get("/api/v1/data/export")
    assert exp.status_code == 200
    bundle = exp.json()
    assert bundle["schema"] == 1
    assert len(bundle["activities"]) == 1
    assert bundle["household"]["members"][0]["count"] == 2

    # Dry run returns counts without mutating DB
    bundle["household"]["members"][0]["count"] = 5
    dry = local_client.post("/api/v1/data/import?dry_run=true", json=bundle)
    assert dry.status_code == 200
    assert dry.json()["dry_run"] is True
    assert dry.json()["counts"]["activities"] == 1

    hh_before = local_client.get("/api/v1/household").json()
    assert hh_before["members"][0]["count"] == 2

    # Actual import applies the change
    imp = local_client.post("/api/v1/data/import?dry_run=false", json=bundle)
    assert imp.status_code == 200
    assert imp.json()["dry_run"] is False
    assert imp.json()["imported"]["activities"] == 1

    hh_after = local_client.get("/api/v1/household").json()
    assert hh_after["members"][0]["count"] == 5


def test_import_unknown_schema_returns_409(local_client: TestClient) -> None:
    """Unknown schema version returns 409 Conflict."""
    _setup_data(local_client)
    resp = local_client.post("/api/v1/data/import", json={"schema": 99, "household": {}})
    assert resp.status_code == 409


def test_import_oversize_returns_413(local_client: TestClient) -> None:
    """Payloads larger than 5 MB return 413."""
    big = b"{" + b" " * (5 * 1024 * 1024 + 10) + b"}"
    resp = local_client.post(
        "/api/v1/data/import",
        content=big,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
