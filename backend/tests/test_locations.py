"""Tests for GET /api/v1/locations/search geocoding proxy, caching, and rate limit."""

import json
from pathlib import Path

import httpx
import respx
from app.aqi.pipeline import to_utc_iso, utc_now
from app.config import Settings
from app.db.models import AqiObservation
from app.main import create_app
from app.providers.geocoding import GEOCODING_URL
from fastapi.testclient import TestClient
from sqlmodel import Session

FIXTURES = Path(__file__).parent / "fixtures"


@respx.mock
def test_location_search_filters_india_caches_24h_and_uses_warm_cpcb(tmp_path: Path) -> None:
    fixture = json.loads((FIXTURES / "geocoding_noida.json").read_text(encoding="utf-8"))
    # Include a non-Indian row to prove country_code=IN filtering
    fixture["results"].append(
        {
            "id": 999,
            "name": "Noida Foreign",
            "latitude": 40.0,
            "longitude": -74.0,
            "country_code": "US",
            "admin1": "NJ",
        }
    )
    route = respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=fixture))

    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "loc.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        # Cold CPCB cache -> nearest_station_km is None
        first = client.get("/api/v1/locations/search?q=Noida")
        assert first.status_code == 200
        items = first.json()
        assert len(items) == 5
        assert all(item["label"] != "Noida Foreign" for item in items)
        assert items[0]["nearest_station_km"] is None
        assert route.call_count == 1

        # Second identical query hits 24h cache with 0 new HTTP requests
        second = client.get("/api/v1/locations/search?q=noida")
        assert second.status_code == 200
        assert route.call_count == 1

        # Warm CPCB cache populates nearest_station_km without any network call
        with Session(app.state.engine) as session:
            now_iso = to_utc_iso(utc_now())
            session.add(
                AqiObservation(
                    source_id="cpcb",
                    station_id="st-noida",
                    lat_r=28.62,
                    lon_r=77.36,
                    observed_at=now_iso,
                    kind="current",
                    source_label="Measured",
                    pollutants={"values": {"pm25": 100.0}, "lat": 28.6245, "lon": 77.3577},
                    aqi=233,
                    fetched_at=now_iso,
                )
            )
            session.commit()

        warm = client.get("/api/v1/locations/search?q=Noida")
        assert warm.status_code == 200
        assert warm.json()[0]["nearest_station_km"] is not None


@respx.mock
def test_location_search_502_and_30_per_min_rate_limit(tmp_path: Path) -> None:
    route = respx.get(GEOCODING_URL).mock(return_value=httpx.Response(503))
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "loc_err.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        err = client.get("/api/v1/locations/search?q=Noida")
        assert err.status_code == 502
        assert err.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"

        # 1st request above counted toward the 30/min window; 29 more fill it, 31st hits 429.
        route.mock(return_value=httpx.Response(200, json={"results": []}))
        for idx in range(29):
            r = client.get(f"/api/v1/locations/search?q=City{idx:02d}")
            assert r.status_code == 200
        limited = client.get("/api/v1/locations/search?q=City31")
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
