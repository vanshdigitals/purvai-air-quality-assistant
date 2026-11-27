"""Tests for /air/forecast, /plan, GRAP via location, and PURVAI_FAKE_PROVIDERS."""

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


@respx.mock
@freeze_time("2026-11-25T05:00:00Z")
def test_air_forecast_hourly_lowest_and_30min_cache(tmp_path: Path) -> None:
    om_route = respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )

    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "forecast.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/air/forecast?lat=51.5&lon=-0.12").status_code == 422
        assert client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=49").status_code == 422

        resp = client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=12")
        assert resp.status_code == 200
        assert om_route.call_count == 1
        body = resp.json()
        assert body["scale"] == "CPCB_NAQI"
        assert body["source_label"] == "Modelled"
        assert body["indicative"] is True
        assert body["attribution"] == ["Open-Meteo", "CAMS"]
        assert len(body["hours"]) == 12
        assert body["hours"][0]["time"] == "2026-11-25T05:00:00Z"
        assert body["lowest"]["aqi"] == min(h["aqi"] for h in body["hours"])

        # Cached within 30 min -> 0 HTTP requests
        resp2 = client.get("/api/v1/air/forecast?lat=28.62&lon=77.37&hours=12")
        assert resp2.status_code == 200
        assert om_route.call_count == 1


@respx.mock
@freeze_time("2026-11-25T08:00:00Z")  # 13:30 IST (Afternoon on 2026-11-25)
def test_plan_today_and_tomorrow_ist_periods_persistence_and_409(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    # Build current + forecast responses cleanly
    current_om = _load_fixture("open_meteo_noida.json")
    forecast_om = _load_fixture("open_meteo_forecast_noida.json")
    # Make CPCB observed_at stale (03:30Z is 4.5h before 08:00Z) so current /air uses Open-Meteo
    # Set Open-Meteo current PM2.5 to 260 (Severe 401+) so current afternoon period upgrades!
    assert isinstance(current_om["current"], dict)
    current_om["current"]["time"] = "2026-11-25T07:30"
    current_om["current"]["pm2_5"] = 260.0

    def om_side_effect(request: httpx.Request) -> httpx.Response:
        if "hourly" in request.url.params:
            return httpx.Response(200, json=forecast_om)
        return httpx.Response(200, json=current_om)

    respx.get(OPEN_METEO_AIR_URL).mock(side_effect=om_side_effect)

    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "plan.db"),
            data_gov_in_api_key="key",  # type: ignore[arg-type]
            gemini_api_key=None,
            groq_api_key=None,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        # 409 without household
        missing = client.post("/api/v1/plan", json={"day": "today"})
        assert missing.status_code == 409
        assert missing.json()["error"]["code"] == "HOUSEHOLD_REQUIRED"

        # Create household in Noida with child
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

        today_resp = client.post("/api/v1/plan", json={"day": "today"})
        assert today_resp.status_code == 200
        today_body = today_resp.json()
        assert today_body["plan_date"] == "2026-11-25"
        assert today_body["generated_by"] == "rules"
        assert len(today_body["periods"]) == 4

        morning, afternoon, evening, night = today_body["periods"]
        assert morning["period"] == "morning"
        assert morning["past"] is True
        assert morning["items"] == []

        # Afternoon is current (13:30 IST) -> current /air AQI (401) overrides forecast
        assert afternoon["period"] == "afternoon"
        assert afternoon["past"] is False
        assert afternoon["aqi"] == 401
        assert afternoon["level"] == "severe"
        assert all(item["tag"] == "rule" for item in afternoon["items"])

        assert evening["period"] == "evening"
        assert evening["past"] is False
        assert night["period"] == "night"
        assert night["start"] == "21:00"
        assert night["end"] == "06:00"

        # Rebuild tomorrow plan -> stored in daily_plan as Modelled
        tmrw_resp = client.post("/api/v1/plan", json={"day": "tomorrow"})
        assert tmrw_resp.status_code == 200
        tmrw_body = tmrw_resp.json()
        assert tmrw_body["plan_date"] == "2026-11-26"
        assert tmrw_body["source_label"] == "Modelled"
        assert all(p["past"] is False for p in tmrw_body["periods"])

        # Rebuilding today replaces existing plan_item rows cleanly
        rebuilt = client.post("/api/v1/plan", json={"day": "today"})
        assert rebuilt.status_code == 200

        with Session(app.state.engine) as session:
            plans = session.exec(select(DailyPlan)).all()
            assert len(plans) == 2
            assert all(p.generated_by == "rules" for p in plans)
            items = session.exec(select(PlanItem)).all()
            assert len(items) > 0


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
        client.put(
            "/api/v1/household",
            json={
                "members": [{"kind": "adult", "count": 1}],
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
        air = client.get("/api/v1/air?lat=28.6271&lon=77.3716")
        assert air.status_code == 200
        body = air.json()
        assert body["source_label"] == "Modelled"
        assert body["grap"] == {
            "stage": "II",
            "order_date": "2026-11-02",
            "source_url": "https://caqm.nic.in/",
        }


def test_fake_providers_refused_in_demo_mode_and_works_offline_in_local(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="PURVAI_FAKE_PROVIDERS"):
        create_app(
            Settings(
                purvai_mode="demo",
                purvai_fake_providers=True,
                database_path=str(tmp_path / "bad_fake.db"),
            )
        )

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
