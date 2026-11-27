"""Tests for Home Air ACH calculator, deterministic indoor tips, and ISO UTC ventilation hour."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from app.config import Settings
from app.main import create_app
from app.providers.cpcb import CPCB_RESOURCE_URL
from app.providers.open_meteo import OPEN_METEO_AIR_URL
from app.rules.catalogue import Category
from app.rules.home_air import HOME_AIR_TIPS, get_home_air_tips
from fastapi.testclient import TestClient
from freezegun import freeze_time

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_home_air_calc_worked_example_1_meets_target(local_client: TestClient) -> None:
    """Worked example 1: 3.5 x 3.0 x 2.8, CADR 250 -> 29.4, 8.5, meets_target=True, 147."""
    r = local_client.post(
        "/api/v1/home-air/calc",
        json={"length_m": 3.5, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 250},
    )
    assert r.status_code == 200
    assert r.json() == {
        "volume_m3": 29.4,
        "ach": 8.5,
        "target_ach": 5,
        "meets_target": True,
        "cadr_needed_m3h": 147,
    }


def test_home_air_calc_worked_example_2_below_target(local_client: TestClient) -> None:
    """Worked example 2: 4 x 4 x 3, CADR 200 -> 48.0, 4.2, meets_target=False, 240."""
    r = local_client.post(
        "/api/v1/home-air/calc",
        json={"length_m": 4.0, "width_m": 4.0, "height_m": 3.0, "cadr_m3h": 200},
    )
    assert r.status_code == 200
    assert r.json() == {
        "volume_m3": 48.0,
        "ach": 4.2,
        "target_ach": 5,
        "meets_target": False,
        "cadr_needed_m3h": 240,
    }


def test_home_air_calc_range_boundaries(local_client: TestClient) -> None:
    """Minimum and maximum documented boundaries accept cleanly."""
    r_min = local_client.post(
        "/api/v1/home-air/calc",
        json={"length_m": 0.5, "width_m": 0.5, "height_m": 1.5, "cadr_m3h": 20},
    )
    assert r_min.status_code == 200
    assert r_min.json()["volume_m3"] == 0.4

    r_max = local_client.post(
        "/api/v1/home-air/calc",
        json={"length_m": 50.0, "width_m": 50.0, "height_m": 10.0, "cadr_m3h": 2000},
    )
    assert r_max.status_code == 200
    assert r_max.json()["volume_m3"] == 25000.0


@pytest.mark.parametrize(
    "payload",
    [
        {"length_m": 0.49, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 250},
        {"length_m": 50.1, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 250},
        {"length_m": 3.5, "width_m": 0.49, "height_m": 2.8, "cadr_m3h": 250},
        {"length_m": 3.5, "width_m": 50.1, "height_m": 2.8, "cadr_m3h": 250},
        {"length_m": 3.5, "width_m": 3.0, "height_m": 1.49, "cadr_m3h": 250},
        {"length_m": 3.5, "width_m": 3.0, "height_m": 10.1, "cadr_m3h": 250},
        {"length_m": 3.5, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 19.9},
        {"length_m": 3.5, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 2000.1},
        {"length_m": 3.5, "width_m": 3.0, "height_m": 2.8, "cadr_m3h": 250, "extra": 1},
    ],
)
def test_home_air_calc_validation_422s(
    local_client: TestClient, payload: dict[str, float | int]
) -> None:
    resp = local_client.post("/api/v1/home-air/calc", json=payload)
    assert resp.status_code == 422


@pytest.mark.parametrize(
    ("level", "expected_ids"),
    [
        (
            "good",
            ["cooking_exhaust", "ventilate_low_hour"],
        ),
        (
            "satisfactory",
            ["cooking_exhaust", "ventilate_low_hour"],
        ),
        (
            "moderate",
            ["wet_mopping", "cooking_exhaust", "ventilate_low_hour"],
        ),
        (
            "poor",
            [t[0] for t in HOME_AIR_TIPS],
        ),
        (
            "very_poor",
            [t[0] for t in HOME_AIR_TIPS],
        ),
        (
            "severe",
            [t[0] for t in HOME_AIR_TIPS],
        ),
    ],
)
def test_home_air_tips_for_every_aqi_level(level: Category, expected_ids: list[str]) -> None:
    res = get_home_air_tips(level, ventilation_hour="2026-11-27T11:00:00Z")
    assert res.level == level
    assert [tip.tip_id for tip in res.tips] == expected_ids
    assert res.ventilation_hour == "2026-11-27T11:00:00Z"
    assert any("16:30 IST" in tip.text for tip in res.tips)
    for tip in res.tips:
        assert "safe" not in tip.text.lower()


@respx.mock
@freeze_time("2026-11-27T04:00:00Z")
def test_home_air_tips_ventilation_window_08_to_20_ist_returns_iso_utc(tmp_path: Path) -> None:
    """Exclude hours outside 08:00..20:00 IST and return ISO 8601 UTC timestamp."""
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )

    # Craft hourly forecast where cleanest hours are outside 08:00..20:00 IST,
    # except 11:00Z (16:30 IST) which must win!
    times = [
        "2026-11-27T02:00",  # 07:30 IST (before 08:00, very low AQI -> must be ignored)
        "2026-11-27T03:00",  # 08:30 IST (higher AQI)
        "2026-11-27T11:00",  # 16:30 IST (lowest in daytime window -> must win)
        "2026-11-27T14:30",  # 20:00 IST (edge inside window, higher AQI)
        "2026-11-27T15:00",  # 20:30 IST (after 20:00, very low AQI -> must be ignored)
    ]
    custom_forecast = {
        "hourly": {
            "time": times,
            "pm2_5": [5.0, 95.0, 40.0, 100.0, 5.0],
            "pm10": [10.0, 120.0, 60.0, 130.0, 10.0],
            "nitrogen_dioxide": [10.0, 20.0, 15.0, 20.0, 10.0],
            "ozone": [10.0, 20.0, 15.0, 20.0, 10.0],
            "carbon_monoxide": [500.0, 600.0, 500.0, 600.0, 500.0],
            "sulphur_dioxide": [10.0, 20.0, 15.0, 20.0, 10.0],
        }
    }
    respx.get(OPEN_METEO_AIR_URL).mock(return_value=httpx.Response(200, json=custom_forecast))

    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "tips_ist.db"),
            data_gov_in_api_key="key",  # type: ignore[arg-type]
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        resp = client.get("/api/v1/home-air/tips?lat=28.62&lon=77.37")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ventilation_hour"] == "2026-11-27T11:00:00Z"
        assert body["tips"]
