"""Tests for ITF-2023 emission factor seed, activity log, and CO2 impact summary (FR-11)."""

import pytest
from app.config import Settings
from app.db.models import EmissionFactor
from app.main import create_app
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _create_household(client: TestClient, headers: dict[str, str] | None = None) -> None:
    resp = client.put(
        "/api/v1/household",
        headers=headers or {},
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


def test_emission_factor_seed_has_exact_11_modes_and_is_idempotent(
    local_client: TestClient,
) -> None:
    """Migration 0003 seeds exactly 11 ITF-2023 rows and runs idempotently."""
    engine = local_client.app.state.engine  # type: ignore[union-attr]
    with Session(engine) as session:
        rows = session.exec(
            select(EmissionFactor).where(EmissionFactor.version == "ITF-2023")
        ).all()
    assert len(rows) == 11
    modes = {r.mode: r.g_co2e_per_pkm for r in rows}
    assert modes == {
        "car_petrol": 162.0,
        "scooter": 74.0,
        "motorcycle": 65.0,
        "auto_cng": 75.0,
        "auto_diesel": 104.0,
        "bus_diesel": 28.0,
        "bus_diesel_ac": 46.0,
        "bus_cng": 31.0,
        "metro": 24.0,
        "walk": 0.0,
        "cycle": 0.0,
    }

    # Re-running migration 0003 upgrade is idempotent
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
    )
    db_path = local_client.app.state.settings.resolved_database_path  # type: ignore[union-attr]
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(alembic_cfg, "head")
    with Session(engine) as session:
        rows_after = session.exec(select(EmissionFactor)).all()
    assert len(rows_after) == 11


@pytest.mark.parametrize(
    ("mode", "replaced_mode", "distance_km", "expected_saved_g"),
    [
        ("metro", "car_petrol", 10.0, 1380.0),
        ("cycle", "scooter", 5.0, 370.0),
        ("walk", "motorcycle", 2.0, 130.0),
        ("bus_diesel", "car_petrol", 10.0, 1340.0),
        ("bus_cng", "auto_diesel", 10.0, 730.0),
        ("bus_diesel_ac", "car_petrol", 10.0, 1160.0),
        ("auto_cng", "car_petrol", 10.0, 870.0),
        ("bus", "car", 10.0, 1340.0),  # commute_mode alias map
        ("car_petrol", "metro", 10.0, -1380.0),  # negative CO2 when mode is worse
    ],
)
def test_factor_maths_for_mode_pairs_and_negative_co2(
    local_client: TestClient,
    mode: str,
    replaced_mode: str,
    distance_km: float,
    expected_saved_g: float,
) -> None:
    """Factor maths computes positive and negative CO2 savings for all mode pairs."""
    _create_household(local_client)
    resp = local_client.post(
        "/api/v1/activities",
        json={
            "kind": "commute",
            "mode": mode,
            "replaced_mode": replaced_mode,
            "distance_km": distance_km,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["co2_saved_g"] == pytest.approx(expected_saved_g)


def test_co2_null_when_disabled(tmp_path: object) -> None:
    """When CO2_ESTIMATES_ENABLED=false, co2_saved_g is null."""
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "no_co2.db"),
            co2_estimates_enabled=False,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _create_household(client)
        resp = client.post(
            "/api/v1/activities",
            json={
                "kind": "commute",
                "mode": "metro",
                "replaced_mode": "car_petrol",
                "distance_km": 10.0,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["co2_saved_g"] is None


def test_activities_crud_summary_and_demo_isolation(
    local_client: TestClient,
    demo_client: TestClient,
) -> None:
    """Summary totals equal row sums; demo households are isolated on activities."""
    _create_household(local_client)
    r1 = local_client.post(
        "/api/v1/activities",
        json={
            "kind": "commute",
            "mode": "metro",
            "replaced_mode": "car_petrol",
            "distance_km": 10.0,
        },
    )
    r2 = local_client.post(
        "/api/v1/activities",
        json={"kind": "commute", "mode": "cycle", "replaced_mode": "scooter", "distance_km": 5.0},
    )
    assert r1.status_code == 201 and r2.status_code == 201

    rows = local_client.get("/api/v1/activities?days=7").json()
    summary = local_client.get("/api/v1/impact/summary?days=7").json()
    assert summary["trips"] == len(rows)
    assert summary["co2_saved_g"] == pytest.approx(sum(r["co2_saved_g"] for r in rows))
    assert summary["distance_km"] == pytest.approx(sum(r["distance_km"] for r in rows))

    # Demo isolation: household A cannot see or delete household B's activity
    h_a = {"X-Purvai-Household": "11111111-1111-4111-8111-111111111111"}
    h_b = {"X-Purvai-Household": "22222222-2222-4222-8222-222222222222"}
    _create_household(demo_client, headers=h_a)
    _create_household(demo_client, headers=h_b)
    act_a = demo_client.post(
        "/api/v1/activities",
        headers=h_a,
        json={"kind": "commute", "mode": "walk", "replaced_mode": "car_petrol", "distance_km": 2.0},
    ).json()
    assert demo_client.get("/api/v1/activities", headers=h_b).json() == []
    assert demo_client.delete(f"/api/v1/activities/{act_a['id']}", headers=h_b).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "", "distance_km": 5.0},
        {"kind": "commute", "distance_km": -1.0},
        {"kind": "commute", "distance_km": 501.0},
        {"kind": "outdoor", "hours": -0.5},
        {"kind": "outdoor", "hours": 25.0},
        {"kind": "commute", "mode": "teleport", "distance_km": 5.0},
    ],
)
def test_activities_422_variants(local_client: TestClient, payload: dict[str, object]) -> None:
    """Every invalid activity input returns 422."""
    _create_household(local_client)
    resp = local_client.post("/api/v1/activities", json=payload)
    assert resp.status_code == 422


def test_get_all_factors_and_comparison(local_client: TestClient) -> None:
    """get_all_factors returns 11 rows and /impact/compare computes savings vs car_petrol."""
    from app.impact.factors import get_all_factors

    _create_household(local_client)
    engine = local_client.app.state.engine  # type: ignore[union-attr]
    with Session(engine) as session:
        assert len(get_all_factors(session)) == 11

    local_client.post(
        "/api/v1/activities",
        json={
            "kind": "commute",
            "mode": "metro",
            "replaced_mode": "car_petrol",
            "distance_km": 10.0,
        },
    )
    cmp_resp = local_client.get("/api/v1/impact/compare?days=7")
    assert cmp_resp.status_code == 200
    assert cmp_resp.json()["saved_vs_car_g"] == 1380.0
