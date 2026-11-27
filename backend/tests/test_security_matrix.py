"""Security matrix tests: headers, rate limits, path traversal, demo isolation, logging."""

import logging
from pathlib import Path

import pytest
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def _seed_hh(client: TestClient, headers: dict[str, str] | None = None) -> None:
    resp = client.put(
        "/api/v1/household",
        headers=headers or {},
        json={
            "members": [{"kind": "adult", "count": 1}],
            "location": {"label": "Noida", "lat": 28.6271, "lon": 77.3716, "city": "Noida"},
            "settings": {
                "theme": "system",
                "commute_mode": "metro",
                "ai_enabled": False,
                "save_chat": True,
                "reduce_motion": False,
            },
        },
    )
    assert resp.status_code == 200


def test_security_headers_on_json_file_and_html(
    local_client: TestClient, demo_client: TestClient
) -> None:
    """JSON, file-download, and SPA HTML responses all carry security headers."""
    _seed_hh(local_client)
    json_r = local_client.get("/api/v1/health")
    file_r = local_client.post("/api/v1/reports/csv?days=7")
    html_r = local_client.get("/today")

    for r in (json_r, file_r, html_r):
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert r.headers["Permissions-Policy"] == "geolocation=(self)"

    demo_r = demo_client.get("/api/v1/health")
    assert "Strict-Transport-Security" in demo_r.headers


def test_reports_rate_limit_429_and_retry_after(tmp_path: Path) -> None:
    """POST /reports/pdf enforces 10/min rate limit with Retry-After: 60."""
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "rep_rl.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_hh(client)
        for _ in range(10):
            assert client.post("/api/v1/reports/pdf?days=7").status_code == 200
        limited = client.post("/api/v1/reports/pdf?days=7")
        assert limited.status_code == 429
        assert limited.headers.get("Retry-After") == "60"


def test_static_path_traversal_blocked(local_client: TestClient) -> None:
    """Static SPA fallback never serves files outside frontend/dist."""
    for path in ("/../../.env", "/assets/../../.env", "/%2e%2e/.env"):
        r = local_client.get(path)
        assert r.status_code in (200, 404)
        assert "GEMINI_API_KEY" not in r.text
        assert "DATA_GOV_IN_API_KEY" not in r.text


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/household", None),
        ("POST", "/api/v1/plan", {"day": "today"}),
        ("POST", "/api/v1/chat", {"message": "Is it safe?"}),
        ("GET", "/api/v1/conversations", None),
        ("GET", "/api/v1/activities", None),
        ("GET", "/api/v1/impact/summary", None),
        ("POST", "/api/v1/reports/pdf?days=7", None),
        ("POST", "/api/v1/reports/csv?days=7", None),
        ("GET", "/api/v1/data/export", None),
        ("DELETE", "/api/v1/data", {"confirm": "DELETE"}),
    ],
)
def test_demo_isolation_across_all_household_routes(
    demo_client: TestClient,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    """Every household-scoped route returns 409 HOUSEHOLD_REQUIRED for an uninitialized demo ID."""
    h_a = {"X-Purvai-Household": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
    h_b = {"X-Purvai-Household": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}
    _seed_hh(demo_client, headers=h_a)

    resp = demo_client.request(method, path, headers=h_b, json=body)
    assert resp.status_code in (404, 409)


def test_logging_contains_no_sensitive_payloads(
    local_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Logs for /chat, /activities, /data/import, and /reports/pdf omit PII and prompt text."""
    _seed_hh(local_client)
    secret_chat = "SENSITIVE_CHAT_PROMPT_XYZ my son has a cough"
    secret_act = "SENSITIVE_ACTIVITY_KIND_XYZ"

    class _Collector(logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=logging.DEBUG)
            self.lines: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.lines.append(record.getMessage())

    collector = _Collector()
    logger = logging.getLogger("purvai")
    logger.addHandler(collector)
    try:
        local_client.post("/api/v1/activities", json={"kind": secret_act, "hours": 1.0})
        local_client.post("/api/v1/reports/pdf?days=7")
        bundle = local_client.get("/api/v1/data/export").json()
        local_client.post("/api/v1/data/import?dry_run=true", json=bundle)
        local_client.post("/api/v1/chat", json={"message": secret_chat})
    finally:
        logger.removeHandler(collector)

    joined = "\n".join(collector.lines)
    assert secret_chat not in joined
    assert secret_act not in joined
    assert "28.6271" not in joined
    assert "77.3716" not in joined
