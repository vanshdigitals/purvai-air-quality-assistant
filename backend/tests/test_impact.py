"""Tests for ITF-2023 emission factor seed, activity log, and CO2 impact summary (FR-11)."""

from app.db.models import EmissionFactor
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _create_household(client: TestClient) -> None:
    resp = client.put(
        "/api/v1/household",
        json={
            "members": [{"kind": "adult", "count": 1}],
            "location": {
                "label": "Noida",
                "lat": 28.6271,
                "lon": 77.3716,
                "city": "Noida",
            },
            "settings": {
                "theme": "system",
                "commute_mode": "metro",
                "ai_enabled": False,
                "save_chat": False,
                "reduce_motion": False,
            },
        },
    )
    assert resp.status_code == 200


def test_emission_factor_seed_present(local_client: TestClient) -> None:
    """Migration 0003 seeds all 11 ITF-2023 emission factors."""
    engine = local_client.app.state.engine  # type: ignore[union-attr]
    with Session(engine) as session:
        rows = session.exec(
            select(EmissionFactor).where(EmissionFactor.version == "ITF-2023")
        ).all()
    modes = {r.mode: r.g_co2e_per_pkm for r in rows}
    assert modes["car_petrol"] == 162.0
    assert modes["metro"] == 24.0
    assert modes["walk"] == 0.0
    assert modes["cycle"] == 0.0
    assert modes["bus_diesel"] == 28.0
    assert len(rows) >= 11


def test_activities_crud_and_impact_summary(local_client: TestClient) -> None:
    """POST/GET/DELETE /activities and GET /impact/summary compute ITF-2023 CO2 savings."""
    _create_household(local_client)

    # 10 km metro replacing car_petrol: (162 - 24) * 10 = 1380 g
    r1 = local_client.post(
        "/api/v1/activities",
        json={
            "kind": "commute",
            "mode": "metro",
            "replaced_mode": "car_petrol",
            "distance_km": 10.0,
        },
    )
    assert r1.status_code == 201
    act1 = r1.json()
    assert act1["co2_saved_g"] == 1380.0

    # 5 km cycle replacing scooter: (74 - 0) * 5 = 370 g
    r2 = local_client.post(
        "/api/v1/activities",
        json={
            "kind": "commute",
            "mode": "cycle",
            "replaced_mode": "scooter",
            "distance_km": 5.0,
        },
    )
    assert r2.status_code == 201
    act2 = r2.json()
    assert act2["co2_saved_g"] == 370.0

    # List activities
    r_list = local_client.get("/api/v1/activities?days=7")
    assert r_list.status_code == 200
    assert len(r_list.json()) == 2

    # Summary
    r_sum = local_client.get("/api/v1/impact/summary?days=7")
    assert r_sum.status_code == 200
    summary = r_sum.json()
    assert summary["trips"] == 2
    assert summary["co2_saved_g"] == 1750.0
    assert summary["co2_saved_kg"] == 1.75
    assert summary["distance_km"] == 15.0

    # Delete first activity
    r_del = local_client.delete(f"/api/v1/activities/{act1['id']}")
    assert r_del.status_code == 204

    r_sum2 = local_client.get("/api/v1/impact/summary?days=7")
    assert r_sum2.status_code == 200
    assert r_sum2.json()["trips"] == 1
    assert r_sum2.json()["co2_saved_g"] == 370.0


def test_activities_validation_and_404(local_client: TestClient) -> None:
    """Invalid distance or missing activity returns 422 / 404."""
    _create_household(local_client)

    bad = local_client.post(
        "/api/v1/activities",
        json={"kind": "commute", "mode": "metro", "distance_km": 999.0},
    )
    assert bad.status_code == 422

    missing = local_client.delete("/api/v1/activities/99999")
    assert missing.status_code == 404
