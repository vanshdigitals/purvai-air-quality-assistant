"""Provider parsing, pagination, NA handling, and IST->UTC tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from app.providers.base import ProviderError
from app.providers.cpcb import CPCB_RESOURCE_URL, fetch_cpcb_stations, parse_cpcb_records
from app.providers.open_meteo import parse_open_meteo_payload

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_parse_cpcb_noida_delhi_prayagraj_fixtures() -> None:
    noida_payload = _load_fixture("cpcb_noida_synthetic.json")
    noida_readings = parse_cpcb_records(noida_payload["records"])  # type: ignore[arg-type]
    assert len(noida_readings) == 2
    sector62 = next(r for r in noida_readings if "62" in r.station_name)
    assert sector62.city == "Noida"
    # 25-11-2026 09:00:00 IST == 2026-11-25T03:30:00Z
    assert sector62.observed_at == datetime(2026, 11, 25, 3, 30, tzinfo=UTC)
    assert sector62.pollutants == {
        "pm25": 135.0,
        "pm10": 210.0,
        "no2": 52.0,
        "so2": 14.0,
        "co": 1.6,
    }
    assert "o3" not in sector62.pollutants  # NA skipped

    delhi_payload = _load_fixture("cpcb_delhi_synthetic.json")
    delhi_readings = parse_cpcb_records(delhi_payload["records"])  # type: ignore[arg-type]
    assert len(delhi_readings) == 1
    assert delhi_readings[0].city == "Delhi"
    assert delhi_readings[0].pollutants["pm25"] == 265.0

    prayagraj_payload = _load_fixture("cpcb_prayagraj_synthetic.json")
    prayagraj_readings = parse_cpcb_records(prayagraj_payload["records"])  # type: ignore[arg-type]
    assert len(prayagraj_readings) == 1
    assert prayagraj_readings[0].city == "Prayagraj"
    assert set(prayagraj_readings[0].pollutants.keys()) == {"pm25", "pm10", "no2"}


@pytest.mark.anyio
@respx.mock
async def test_cpcb_pagination_across_pages() -> None:
    noida_records = _load_fixture("cpcb_noida_synthetic.json")["records"]
    assert isinstance(noida_records, list)
    page1 = noida_records[:5]
    page2 = noida_records[5:]

    route = respx.get(CPCB_RESOURCE_URL).mock(
        side_effect=[
            httpx.Response(200, json={"total": len(noida_records), "records": page1}),
            httpx.Response(200, json={"total": len(noida_records), "records": page2}),
        ]
    )

    readings = await fetch_cpcb_stations("test-key", limit=5)
    assert route.call_count == 2
    assert len(readings) == 2


@pytest.mark.anyio
@respx.mock
async def test_cpcb_http_failure_raises_provider_error() -> None:
    respx.get(CPCB_RESOURCE_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ProviderError):
        await fetch_cpcb_stations("test-key")


def test_parse_open_meteo_fixture() -> None:
    om_payload = _load_fixture("open_meteo_noida.json")
    reading = parse_open_meteo_payload(om_payload)
    assert reading.observed_at == datetime(2026, 11, 25, 3, 0, tzinfo=UTC)
    assert reading.pollutants["pm25"] == pytest.approx(152.4)
    assert reading.pollutants["co"] == pytest.approx(3.794)


def test_parse_cpcb_ist_midnight_aliases_and_edge_cases() -> None:
    records = [
        {
            "station": "Test Station",
            "city": "Delhi",
            "lat": "28.61",
            "lon": "77.20",
            "last_update": "26-11-2026 01:15:00",
            "pollutant_id": "PM2.5",
            "avg_value": "120",
            "unit": "µg/m³",
        },
        {
            "station": "Test Station",
            "city": "Delhi",
            "lat": "28.61",
            "lon": "77.20",
            "last_update": "26-11-2026 01:15:00",
            "pollutant_id": "CO",
            "avg_value": "2000",
            "unit": "ug/m3",
        },
        {
            "station": "Test Station",
            "city": "Delhi",
            "lat": "28.61",
            "lon": "77.20",
            "last_update": "26-11-2026 01:15:00",
            "pollutant_id": "NO2",
            "avg_value": "NA",
        },
        {
            "station": "Test Station",
            "city": "Delhi",
            "lat": "28.61",
            "lon": "77.20",
            "last_update": "26-11-2026 01:15:00",
            "pollutant_id": "SO2",
            "avg_value": "",
        },
        {
            "station": "Test Station",
            "city": "Delhi",
            "lat": "28.61",
            "lon": "77.20",
            "last_update": "26-11-2026 01:15:00",
            "pollutant_id": "PM10",
            "avg_value": "-10",
        },
        {
            "station": "Test Station",
            "city": "Delhi",
            "lat": "28.61",
            "lon": "77.20",
            "last_update": "26-11-2026 01:15:00",
            "pollutant_id": "PB",
            "avg_value": "5",
        },
    ]
    readings = parse_cpcb_records(records)
    assert len(readings) == 1
    # 26-11-2026 01:15:00 IST == 2026-11-25T19:45:00Z UTC (across midnight)
    assert readings[0].observed_at == datetime(2026, 11, 25, 19, 45, tzinfo=UTC)
    assert readings[0].pollutants == {"pm25": 120.0, "co": 2.0}
