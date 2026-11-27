"""Tests for /air/forecast, /plan IST boundaries, GRAP via location, and PURVAI_FAKE_PROVIDERS."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from app.config import Settings
from app.db.models import DailyPlan, PlanItem
from app.main import create_app
from app.providers.cpcb import CPCB_RESOURCE_URL
from app.providers.open_meteo import OPEN_METEO_AIR_URL
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlmodel import Session, select

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _seed_household(client: TestClient) -> None:
    put_resp = client.put(
        "/api/v1/household",
        json={
            "members": [{"kind": "adult", "count": 1}, {"kind": "child_u12", "count": 1}],
            "location": {
                "label": "Sector 62, Noida",
                "lat": 28.6271,
                "lon": 77.3716,
                "city": "Noida",
                "admin1": "Uttar Pradesh",
            },
            "settings": {"theme": "system", "commute_mode": "metro"},
        },
    )
    assert put_resp.status_code == 200


@respx.mock
@freeze_time("2026-11-25T05:00:00Z")
def test_air_forecast_hours_range_and_validation(tmp_path: Path) -> None:
    respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "fc_range.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/air/forecast?lat=51.5&lon=-0.12").status_code == 422
        assert client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=0").status_code == 422
        assert client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=49").status_code == 422

        r1 = client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=1")
        assert r1.status_code == 200
        assert len(r1.json()["hours"]) == 1

        r48 = client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=48")
        assert r48.status_code == 200
        assert len(r48.json()["hours"]) <= 48


@respx.mock
@freeze_time("2026-11-25T05:00:00Z")
def test_air_forecast_cache_hit_and_lowest_hour(tmp_path: Path) -> None:
    om_route = respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "fc_cache.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        first = client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=12")
        assert first.status_code == 200
        assert om_route.call_count == 1
        body = first.json()
        assert body["scale"] == "CPCB_NAQI"
        assert body["source_label"] == "Modelled"
        assert body["indicative"] is True
        assert body["attribution"] == ["Open-Meteo", "CAMS"]
        assert len(body["hours"]) == 12
        assert body["lowest"]["aqi"] == min(h["aqi"] for h in body["hours"])

        second = client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=12")
        assert second.status_code == 200
        assert om_route.call_count == 1


def test_plan_409_without_household(local_client: TestClient) -> None:
    resp = local_client.post("/api/v1/plan", json={"day": "today"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "HOUSEHOLD_REQUIRED"


@respx.mock
@freeze_time("2026-11-25T00:00:00Z")  # 05:30 IST (before Morning starts)
def test_plan_ist_period_boundaries_and_night_across_midnight(tmp_path: Path) -> None:
    """Verify Morning [06-12), Afternoon [12-17), Evening [17-21), Night [21-06 next day) IST."""
    # Boundary UTC timestamps for IST 06:00, 12:00, 17:00, 21:00, 01:00+1d, 06:00+1d
    hourly = {
        "hourly": {
            "time": [
                "2026-11-25T00:30",  # 06:00 IST -> Morning -> PM2.5=20 -> Good (33)
                "2026-11-25T06:30",  # 12:00 IST -> Afternoon -> PM2.5=75 -> Moderate (150)
                "2026-11-25T11:30",  # 17:00 IST -> Evening -> PM2.5=100 -> Poor (233)
                "2026-11-25T15:30",  # 21:00 IST -> Night -> PM2.5=15 -> Good (25)
                "2026-11-25T19:30",  # 01:00 IST (Nov 26) -> Night -> PM2.5=260 -> Severe (401)
                "2026-11-26T00:30",  # 06:00 IST (Nov 26) -> Next Morning (excluded from Night)
            ],
            "pm2_5": [20.0, 75.0, 100.0, 15.0, 260.0, 10.0],
            "pm10": [20.0, 75.0, 100.0, 15.0, 260.0, 10.0],
            "nitrogen_dioxide": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
            "ozone": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
            "carbon_monoxide": [500.0, 500.0, 500.0, 500.0, 500.0, 500.0],
            "sulphur_dioxide": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
        }
    }
    current_om = _load_fixture("open_meteo_noida.json")
    assert isinstance(current_om["current"], dict)
    current_om["current"]["time"] = "2026-11-24T23:30"
    respx.get(OPEN_METEO_AIR_URL).mock(
        side_effect=lambda req: (
            httpx.Response(200, json=hourly)
            if "hourly" in req.url.params
            else httpx.Response(200, json=current_om)
        )
    )

    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "plan_boundaries.db"),
            data_gov_in_api_key=None,
            gemini_api_key=None,
            groq_api_key=None,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client)
        res = client.post("/api/v1/plan", json={"day": "today"})
        assert res.status_code == 200
        morning, afternoon, evening, night = res.json()["periods"]

        assert (morning["start"], morning["end"], morning["level"]) == ("06:00", "12:00", "good")
        assert (afternoon["start"], afternoon["end"], afternoon["level"]) == (
            "12:00",
            "17:00",
            "moderate",
        )
        assert (evening["start"], evening["end"], evening["level"]) == ("17:00", "21:00", "poor")
        assert (night["start"], night["end"], night["level"], night["aqi"]) == (
            "21:00",
            "06:00",
            "severe",
            401,
        )


@respx.mock
@freeze_time("2026-11-25T08:00:00Z")  # 13:30 IST (Afternoon)
def test_plan_worst_hour_level_and_current_period_override(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    current_om = _load_fixture("open_meteo_noida.json")
    assert isinstance(current_om["current"], dict)
    current_om["current"]["time"] = "2026-11-25T07:30"
    current_om["current"]["pm2_5"] = 260.0  # Severe 401+

    forecast_om = _load_fixture("open_meteo_forecast_noida.json")
    respx.get(OPEN_METEO_AIR_URL).mock(
        side_effect=lambda req: (
            httpx.Response(200, json=forecast_om)
            if "hourly" in req.url.params
            else httpx.Response(200, json=current_om)
        )
    )

    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "plan_override.db"),
            data_gov_in_api_key="key",  # type: ignore[arg-type]
            gemini_api_key=None,
            groq_api_key=None,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client)
        body = client.post("/api/v1/plan", json={"day": "today"}).json()
        afternoon = body["periods"][1]
        assert afternoon["period"] == "afternoon"
        assert afternoon["aqi"] == 401
        assert afternoon["level"] == "severe"


@respx.mock
@freeze_time("2026-11-25T08:00:00Z")  # 13:30 IST -> Morning is past
def test_plan_past_periods_have_no_items(tmp_path: Path) -> None:
    respx.get(OPEN_METEO_AIR_URL).mock(
        side_effect=lambda req: httpx.Response(
            200,
            json=_load_fixture(
                "open_meteo_forecast_noida.json"
                if "hourly" in req.url.params
                else "open_meteo_noida.json"
            ),
        )
    )
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "plan_past.db"),
            data_gov_in_api_key=None,
            gemini_api_key=None,
            groq_api_key=None,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client)
        body = client.post("/api/v1/plan", json={"day": "today"}).json()
        morning = body["periods"][0]
        assert morning["period"] == "morning"
        assert morning["past"] is True
        assert morning["items"] == []


@respx.mock
@freeze_time("2026-11-25T08:00:00Z")
def test_plan_tomorrow_always_modelled(tmp_path: Path) -> None:
    respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "plan_tmrw.db"),
            data_gov_in_api_key="key",  # type: ignore[arg-type]
            gemini_api_key=None,
            groq_api_key=None,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client)
        tmrw = client.post("/api/v1/plan", json={"day": "tomorrow"})
        assert tmrw.status_code == 200
        body = tmrw.json()
        assert body["plan_date"] == "2026-11-26"
        assert body["source_label"] == "Modelled"
        assert all(p["past"] is False for p in body["periods"])


@respx.mock
@freeze_time("2026-11-25T08:00:00Z")
def test_plan_replace_on_rebuild_and_works_without_ai_keys(tmp_path: Path) -> None:
    respx.get(OPEN_METEO_AIR_URL).mock(
        side_effect=lambda req: httpx.Response(
            200,
            json=_load_fixture(
                "open_meteo_forecast_noida.json"
                if "hourly" in req.url.params
                else "open_meteo_noida.json"
            ),
        )
    )
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "plan_rebuild.db"),
            gemini_api_key=None,
            groq_api_key=None,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client)
        r1 = client.post("/api/v1/plan", json={"day": "today"})
        assert r1.status_code == 200
        assert r1.json()["generated_by"] == "rules"
        with Session(app.state.engine) as session:
            first_count = len(session.exec(select(PlanItem)).all())

        r2 = client.post("/api/v1/plan", json={"day": "today"})
        assert r2.status_code == 200
        with Session(app.state.engine) as session:
            plans = session.exec(select(DailyPlan)).all()
            assert len(plans) == 1
            assert len(session.exec(select(PlanItem)).all()) == first_count


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_grap_via_household_location_city_when_modelled(tmp_path: Path) -> None:
    respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_noida.json"))
    )
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "grap_modelled.db"),
            data_gov_in_api_key=None,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client)
        air = client.get("/api/v1/air?lat=28.6271&lon=77.3716")
        assert air.status_code == 200
        body = air.json()
        assert body["source_label"] == "Modelled"
        assert body["grap"] == {
            "stage": "II",
            "order_date": "2026-11-02",
            "source_url": "https://caqm.nic.in/",
        }


def test_fake_providers_refused_in_demo_mode(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="PURVAI_FAKE_PROVIDERS"):
        create_app(
            Settings(
                purvai_mode="demo",
                purvai_fake_providers=True,
                database_path=str(tmp_path / "bad_fake.db"),
            )
        )


def test_fake_providers_works_offline_in_local_mode(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            purvai_mode="local",
            purvai_fake_providers=True,
            database_path=str(tmp_path / "ok_fake.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        loc_res = client.get("/api/v1/locations/search?q=Noida")
        assert loc_res.status_code == 200
        assert any("Noida" in item["label"] for item in loc_res.json())

        air_res = client.get("/api/v1/air?lat=28.6271&lon=77.3716")
        assert air_res.status_code == 200
        assert air_res.json()["source_label"] == "Measured"

        fc_res = client.get("/api/v1/air/forecast?lat=28.6271&lon=77.3716&hours=12")
        assert fc_res.status_code == 200
        assert len(fc_res.json()["hours"]) == 12
        _ = (UTC, datetime, timedelta)
