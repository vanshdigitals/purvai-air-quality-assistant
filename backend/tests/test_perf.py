"""PERF-01 latency benchmark (50 runs of cached /air, /air/forecast, and /plan)."""

import statistics
import time

import pytest
from fastapi.testclient import TestClient


def _p95(samples_ms: list[float]) -> float:
    ordered = sorted(samples_ms)
    idx = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return ordered[idx]


def test_perf_01_cached_endpoints_p95_under_300ms(
    local_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """50 cached runs of /air, /air/forecast, and /plan (rules) each have p95 < 300 ms."""
    local_client.put(
        "/api/v1/household",
        json={
            "members": [{"kind": "adult", "count": 1}],
            "location": {"label": "Noida", "lat": 28.6271, "lon": 77.3716, "city": "Noida"},
            "settings": {
                "theme": "system",
                "commute_mode": "metro",
                "ai_enabled": False,
                "save_chat": False,
                "reduce_motion": False,
            },
        },
    )

    # Seed fake-provider air + forecast cache once
    from app.config import Settings

    local_client.app.state.settings = Settings(  # type: ignore[union-attr]
        purvai_mode="local",
        database_path=str(local_client.app.state.settings.resolved_database_path),  # type: ignore[union-attr]
        purvai_fake_providers=True,
        rate_limit_per_minute=10000,
    )
    assert local_client.get("/api/v1/air?lat=28.6271&lon=77.3716").status_code == 200
    assert (
        local_client.get("/api/v1/air/forecast?lat=28.6271&lon=77.3716&hours=12").status_code == 200
    )
    assert local_client.post("/api/v1/plan", json={"day": "today"}).status_code == 200

    air_ms: list[float] = []
    forecast_ms: list[float] = []
    plan_ms: list[float] = []

    for _ in range(50):
        t0 = time.perf_counter()
        assert local_client.get("/api/v1/air?lat=28.6271&lon=77.3716").status_code == 200
        air_ms.append((time.perf_counter() - t0) * 1000.0)

        t1 = time.perf_counter()
        assert (
            local_client.get("/api/v1/air/forecast?lat=28.6271&lon=77.3716&hours=12").status_code
            == 200
        )
        forecast_ms.append((time.perf_counter() - t1) * 1000.0)

        t2 = time.perf_counter()
        assert local_client.post("/api/v1/plan", json={"day": "today"}).status_code == 200
        plan_ms.append((time.perf_counter() - t2) * 1000.0)

    print(
        f"\nPERF-01 p95: /air={_p95(air_ms):.2f}ms (med {statistics.median(air_ms):.2f}ms), "
        f"/air/forecast={_p95(forecast_ms):.2f}ms, /plan={_p95(plan_ms):.2f}ms"
    )
    assert _p95(air_ms) < 300.0
    assert _p95(forecast_ms) < 300.0
    assert _p95(plan_ms) < 300.0
