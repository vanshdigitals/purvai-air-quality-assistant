"""Tests for Home Air ACH calculator and deterministic indoor tips."""

import json
from pathlib import Path

import httpx
import respx
from app.config import Settings
from app.main import create_app
from app.providers.cpcb import CPCB_RESOURCE_URL
from app.providers.open_meteo import OPEN_METEO_AIR_URL
from fastapi.testclient import TestClient
from freezegun import freeze_time

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_home_air_calc_worked_examples_and_validation(local_client: TestClient) -> None:
    # Worked example 1: 3.5 x 3.0 x 2.8, CADR 250 -> 29.4, 8.5, meets_target=True, 147
    r1 = local_client.post(
        "/api/v1/home-air/calc",
        json={"length_m": 3.5, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 250},
    )
    assert r1.status_code == 200
    assert r1.json() == {
        "volume_m3": 29.4,
        "ach": 8.5,
        "target_ach": 5,
        "meets_target": True,
        "cadr_needed_m3h": 147,
    }

    # Worked example 2: 4 x 4 x 3, CADR 200 -> 48.0, 4.2, meets_target=False, 240
    r2 = local_client.post(
        "/api/v1/home-air/calc",
        json={"length_m": 4.0, "width_m": 4.0, "height_m": 3.0, "cadr_m3h": 200},
    )
    assert r2.status_code == 200
    assert r2.json() == {
        "volume_m3": 48.0,
        "ach": 4.2,
        "target_ach": 5,
        "meets_target": False,
        "cadr_needed_m3h": 240,
    }

    # Boundary validation 422s
    assert (
        local_client.post(
            "/api/v1/home-air/calc",
            json={"length_m": 0.4, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 250},
        ).status_code
        == 422
    )
    assert (
        local_client.post(
            "/api/v1/home-air/calc",
            json={"length_m": 3.5, "width_m": 3.0, "height_m": 1.2, "cadr_m3h": 250},
        ).status_code
        == 422
    )
    assert (
        local_client.post(
            "/api/v1/home-air/calc",
            json={"length_m": 3.5, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 10},
        ).status_code
        == 422
    )
    assert (
        local_client.post(
            "/api/v1/home-air/calc",
            json={
                "length_m": 3.5,
                "width_m": 3.0,
                "height_m": 2.8,
                "cadr_m3h": 250,
                "extra": 1,
            },
        ).status_code
        == 422
    )


@respx.mock
@freeze_time("2026-11-25T04:00:00Z")  # 09:30 IST -> next 12h covers 09:30..21:30 IST
def test_home_air_tips_by_level_and_ventilation_hour(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )

    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "tips.db"),
            data_gov_in_api_key="key",  # type: ignore[arg-type]
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        resp = client.get("/api/v1/home-air/tips?lat=28.62&lon=77.37")
        assert resp.status_code == 200
        body = resp.json()
        assert body["level"] == "very_poor"
        tip_ids = [t["tip_id"] for t in body["tips"]]
        assert tip_ids == [
            "purifier_closed_room",
            "wet_mopping",
            "cooking_exhaust",
            "avoid_incense",
            "mask_fit",
            "ventilate_low_hour",
        ]
        assert body["ventilation_hour"] is not None
        assert body["ventilation_hour"].endswith("IST")
        hour_num = int(body["ventilation_hour"].split(":")[0])
        assert 8 <= hour_num <= 20
        for tip in body["tips"]:
            assert "safe" not in tip["text"].lower()
