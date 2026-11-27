"""Integration tests for AQI pipeline, caching, fallbacks, GRAP, and /api/v1/air."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx
from app.config import Settings
from app.db.models import AqiObservation, Household, Member
from app.main import create_app
from app.providers.cpcb import CPCB_RESOURCE_URL
from app.providers.open_meteo import OPEN_METEO_AIR_URL
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlmodel import Session, select

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _make_client(
    tmp_path: Path,
    *,
    mode: str = "local",
    api_key: str | None = "test-cpcb-key",
    db_name: str = "air_test.db",
) -> TestClient:
    settings = Settings(
        purvai_mode=mode,  # type: ignore[arg-type]
        database_path=str(tmp_path / db_name),
        data_gov_in_api_key=api_key,  # type: ignore[arg-type]
        rate_limit_per_minute=1000,
    )
    app = create_app(settings)
    return TestClient(app)


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_air_measured_cpcb_noida_with_child_verdict_and_grap(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    om_route = respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_noida.json"))
    )

    with _make_client(tmp_path) as client:
        with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
            hh = Household(mode="local")
            session.add(hh)
            session.commit()
            session.refresh(hh)
            session.add(Member(household_id=hh.id, kind="child_u12", count=1))
            session.commit()

        resp = client.get("/api/v1/air?lat=28.62&lon=77.37")
        assert resp.status_code == 200
        assert om_route.call_count == 0

        body = resp.json()
        assert body["aqi"] == 312
        assert body["aqi_is_floor"] is False
        assert body["category"] == "very_poor"
        assert body["scale"] == "CPCB_NAQI"
        assert body["source_label"] == "Measured"
        assert body["source"]["provider"] == "CPCB"
        assert body["source"]["station"] == "Sector - 62, Noida - IMD"
        assert body["source"]["distance_km"] == 1.3
        assert body["observed_at"] == "2026-11-25T03:30:00Z"
        assert body["age_minutes"] == 40
        assert body["stale"] is False
        assert body["indicative"] is True
        assert body["served_from_cache"] is False
        assert body["dominant_pollutant"] == "pm25"
        assert body["pollutants"]["pm25"] == {"value": 135.0, "unit": "µg/m³", "sub_index": 312}
        assert body["verdict"]["level"] == "very_poor"
        assert body["verdict"]["household_level"] == "severe"
        assert body["verdict"]["headline"] == "Stay indoors today. Run the purifier."
        assert body["verdict"]["action_ids"] == ["stay_indoors", "purifier_on", "n95_if_out"]
        assert body["grap"] == {
            "stage": "II",
            "order_date": "2026-11-02",
            "source_url": "https://caqm.nic.in/",
        }
        assert body["attribution"] == ["CPCB", "data.gov.in"]
        assert "test-cpcb-key" not in resp.text
        assert ".db" not in resp.text

        # Second call within 30 minutes hits SQLite cache with 0 new HTTP requests
        resp2 = client.get("/api/v1/air?lat=28.62&lon=77.37")
        assert resp2.status_code == 200
        assert respx.calls.call_count == 1


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_station_over_10km_falls_back_to_modelled_open_meteo(tmp_path: Path) -> None:
    # Prayagraj station is at (25.4358, 81.8463); request ~12 km east -> 10.1+ km
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_prayagraj_synthetic.json"))
    )
    om_route = respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_noida.json"))
    )

    with _make_client(tmp_path) as client:
        resp = client.get("/api/v1/air?lat=25.4358&lon=81.96")
        assert resp.status_code == 200
        assert om_route.call_count == 1
        body = resp.json()
        assert body["source_label"] == "Modelled"
        assert body["source"] == {
            "provider": "Open-Meteo (CAMS)",
            "station": None,
            "distance_km": None,
        }
        assert body["grap"] is None
        assert body["attribution"] == ["Open-Meteo", "CAMS"]


@respx.mock
def test_stale_cpcb_station_over_2h_uses_modelled_and_then_cache_fallback(tmp_path: Path) -> None:
    cpcb_route = respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    om_route = respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_noida.json"))
    )

    # At 05:31Z, CPCB observed_at 03:30Z is 121 min old (>2h) -> Open-Meteo Modelled
    with freeze_time("2026-11-25T05:31:00Z"):
        with _make_client(tmp_path, db_name="fallback.db") as client:
            first = client.get("/api/v1/air?lat=28.62&lon=77.37")
            assert first.status_code == 200
            assert first.json()["source_label"] == "Modelled"
            assert cpcb_route.call_count == 1
            assert om_route.call_count == 1

    # 3 hours later (outside 30m cache TTL), both providers go down -> serve cache with stale=True
    cpcb_route.mock(return_value=httpx.Response(503))
    om_route.mock(return_value=httpx.Response(503))
    with freeze_time("2026-11-25T08:30:00Z"):
        with _make_client(tmp_path, db_name="fallback.db") as client:
            cached = client.get("/api/v1/air?lat=28.62&lon=77.37")
            assert cached.status_code == 200
            body = cached.json()
            assert body["served_from_cache"] is True
            assert body["stale"] is True
            assert body["age_minutes"] == 330


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_both_providers_down_no_cache_returns_502(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(return_value=httpx.Response(502))
    respx.get(OPEN_METEO_AIR_URL).mock(return_value=httpx.Response(502))

    with _make_client(tmp_path) as client:
        resp = client.get("/api/v1/air?lat=28.62&lon=77.37")
        assert resp.status_code == 502
        body = resp.json()
        assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"
        assert body["error"]["request_id"]


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_missing_api_key_skips_cpcb_and_uses_modelled(tmp_path: Path) -> None:
    om_route = respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_noida.json"))
    )

    with _make_client(tmp_path, api_key=None) as client:
        resp = client.get("/api/v1/air?lat=28.62&lon=77.37")
        assert resp.status_code == 200
        assert om_route.call_count == 1
        assert resp.json()["source_label"] == "Modelled"


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_less_than_three_pollutants_labels_estimated_and_grap_null_outside_ncr(
    tmp_path: Path,
) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_prayagraj_synthetic.json"))
    )
    om_payload = _load_fixture("open_meteo_noida.json")
    assert isinstance(om_payload["current"], dict)
    # Remove gases from Open-Meteo? Keep CPCB with only 2 pollutants instead.
    cpcb_two = {
        "total": 2,
        "records": [
            {
                "country": "India",
                "state": "Uttar Pradesh",
                "city": "Prayagraj",
                "station": "Jhusi, Prayagraj - UPPCB",
                "last_update": "25-11-2026 09:00:00",
                "latitude": "25.4358",
                "longitude": "81.8463",
                "pollutant_id": "PM2.5",
                "pollutant_avg": "82",
            },
            {
                "country": "India",
                "state": "Uttar Pradesh",
                "city": "Prayagraj",
                "station": "Jhusi, Prayagraj - UPPCB",
                "last_update": "25-11-2026 09:00:00",
                "latitude": "25.4358",
                "longitude": "81.8463",
                "pollutant_id": "NO2",
                "pollutant_avg": "34",
            },
        ],
    }
    respx.get(CPCB_RESOURCE_URL).mock(return_value=httpx.Response(200, json=cpcb_two))

    with _make_client(tmp_path) as client:
        resp = client.get("/api/v1/air?lat=25.44&lon=81.85")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_label"] == "Estimated"
        assert body["grap"] is None


@respx.mock
def test_eight_day_purge_on_startup(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )

    with freeze_time("2026-11-25T04:10:00Z"):
        with _make_client(tmp_path, db_name="purge.db") as client:
            assert client.get("/api/v1/air?lat=28.62&lon=77.37").status_code == 200
            with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
                assert len(session.exec(select(AqiObservation)).all()) >= 1

    # Restart 9 days later -> startup purges old observations
    with freeze_time("2026-12-04T05:00:00Z"):
        with _make_client(tmp_path, db_name="purge.db") as client:
            with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
                assert session.exec(select(AqiObservation)).all() == []


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_validation_422_unsupported_region_and_demo_household_scoping(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )

    with _make_client(tmp_path, mode="demo") as client:
        bad_lat = client.get("/api/v1/air?lat=95&lon=77.37")
        assert bad_lat.status_code == 422
        assert bad_lat.json()["error"]["code"] == "VALIDATION_ERROR"

        outside_india = client.get("/api/v1/air?lat=51.5&lon=-0.12")
        assert outside_india.status_code == 422
        assert outside_india.json()["error"]["code"] == "UNSUPPORTED_REGION"
        assert (
            outside_india.json()["error"]["message"]
            == "Purvai currently supports locations in India."
        )

        # Create two isolated demo households
        with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
            hh_a = Household(mode="demo")
            hh_b = Household(mode="demo")
            session.add(hh_a)
            session.add(hh_b)
            session.commit()
            session.refresh(hh_a)
            session.refresh(hh_b)
            session.add(Member(household_id=hh_a.id, kind="child_u12", count=1))
            session.add(Member(household_id=hh_b.id, kind="adult", count=1))
            session.commit()
            id_a, id_b = hh_a.id, hh_b.id

        resp_a = client.get("/api/v1/air?lat=28.62&lon=77.37", headers={"X-Purvai-Household": id_a})
        resp_b = client.get("/api/v1/air?lat=28.62&lon=77.37", headers={"X-Purvai-Household": id_b})
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json()["verdict"]["household_level"] == "severe"
        assert resp_b.json()["verdict"]["household_level"] == "very_poor"


@respx.mock
def test_cpcb_timeout_falls_back_to_open_meteo_in_same_request(tmp_path: Path) -> None:
    async def slow_cpcb(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.3)
        return httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))

    respx.get(CPCB_RESOURCE_URL).mock(side_effect=slow_cpcb)
    om_route = respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_noida.json"))
    )

    settings = Settings(
        purvai_mode="local",
        database_path=str(tmp_path / "timeout.db"),
        data_gov_in_api_key="test-cpcb-key",  # type: ignore[arg-type]
        cpcb_timeout_s=5.0,
        rate_limit_per_minute=1000,
    )
    # Override cpcb_timeout_s post-construction via model_copy to test sub-second overall deadline
    fast_settings = settings.model_copy(update={"cpcb_timeout_s": 0.05})
    app = create_app(fast_settings)
    with TestClient(app) as client:
        resp = client.get("/api/v1/air?lat=28.62&lon=77.37")
        assert resp.status_code == 200
        assert om_route.call_count == 1
        assert resp.json()["source_label"] == "Modelled"


@respx.mock
def test_cpcb_circuit_breaker_open_skip_and_half_open_after_15_minutes(tmp_path: Path) -> None:
    cpcb_route = respx.get(CPCB_RESOURCE_URL).mock(return_value=httpx.Response(503))
    om_route = respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_noida.json"))
    )

    with freeze_time("2026-11-25T04:10:00Z") as frozen:
        with _make_client(tmp_path, db_name="breaker.db") as client:
            breaker = client.app.state.cpcb_breaker  # type: ignore[attr-defined]
            assert breaker.state() == "closed"

            # 1. Failure opens breaker and falls back to Open-Meteo
            r1 = client.get("/api/v1/air?lat=28.62&lon=77.37")
            assert r1.status_code == 200
            assert r1.json()["source_label"] == "Modelled"
            assert cpcb_route.call_count == 1
            assert om_route.call_count == 1
            assert breaker.state() == "open"

            # 2. Cold location at +5 min skips CPCB completely while breaker is open
            frozen.tick(delta=300)
            r2 = client.get("/api/v1/air?lat=25.44&lon=81.85")
            assert r2.status_code == 200
            assert r2.json()["source_label"] == "Modelled"
            assert cpcb_route.call_count == 1
            assert om_route.call_count == 2
            assert breaker.state() == "open"

            # 3. After 15 min (+601s -> 901s elapsed), breaker is half_open and probes CPCB
            frozen.tick(delta=601)
            assert breaker.state() == "half_open"
            cpcb_route.mock(
                return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
            )
            r3 = client.get("/api/v1/air?lat=28.62&lon=77.37")
            assert r3.status_code == 200
            assert r3.json()["source_label"] == "Measured"
            assert cpcb_route.call_count == 2
            assert breaker.state() == "closed"


@respx.mock
@pytest.mark.anyio
async def test_refresh_cpcb_in_background_updates_cache_and_breaker(tmp_path: Path) -> None:
    from app.aqi.pipeline import CpcbCircuitBreaker, refresh_cpcb_in_background

    breaker = CpcbCircuitBreaker()
    settings = Settings(
        purvai_mode="local",
        database_path=str(tmp_path / "bg.db"),
        data_gov_in_api_key="test-cpcb-key",  # type: ignore[arg-type]
    )
    app = create_app(settings)
    with TestClient(app):
        with Session(app.state.engine) as session:
            respx.get(CPCB_RESOURCE_URL).mock(return_value=httpx.Response(503))
            assert (
                await refresh_cpcb_in_background(session, settings=settings, cpcb_breaker=breaker)
                == 0
            )
            assert breaker.state() == "open"
            # Skipped while breaker is open
            assert (
                await refresh_cpcb_in_background(session, settings=settings, cpcb_breaker=breaker)
                == 0
            )

            # Reset breaker -> succeeds and stores rows
            breaker.record_success()
            respx.get(CPCB_RESOURCE_URL).mock(
                return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
            )
            count = await refresh_cpcb_in_background(
                session, settings=settings, cpcb_breaker=breaker
            )
            assert count >= 1
            assert breaker.state() == "closed"
