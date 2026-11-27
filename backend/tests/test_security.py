"""Security headers, request ID, body limit, error shapes, and rate limit tests."""

from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from pydantic import BaseModel


def test_security_headers_and_request_id(local_client: TestClient, demo_client: TestClient) -> None:
    local_resp = local_client.get("/api/v1/health", headers={"X-Request-ID": "req-abc-123"})
    assert local_resp.status_code == 200
    assert local_resp.headers["X-Request-ID"] == "req-abc-123"
    assert "default-src 'self'" in local_resp.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in local_resp.headers["Content-Security-Policy"]
    assert local_resp.headers["X-Frame-Options"] == "DENY"
    assert local_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert local_resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert local_resp.headers["Permissions-Policy"] == "geolocation=(self)"
    assert "Strict-Transport-Security" not in local_resp.headers

    demo_resp = demo_client.get("/api/v1/health")
    assert demo_resp.status_code == 200
    assert demo_resp.headers["X-Request-ID"].startswith("r-")
    assert "Strict-Transport-Security" in demo_resp.headers


def test_unknown_api_route_returns_json_404(local_client: TestClient) -> None:
    resp = local_client.get("/api/v1/unknown")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]


def test_cors_allows_only_configured_dev_origin(
    local_client: TestClient, demo_client: TestClient
) -> None:
    allowed = local_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    disallowed = local_client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert disallowed.headers.get("access-control-allow-origin") is None

    demo_preflight = demo_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert demo_preflight.headers.get("access-control-allow-origin") is None


def test_body_over_64kb_returns_413(local_client: TestClient) -> None:
    oversized = "x" * (64 * 1024 + 1)
    resp = local_client.post("/api/v1/health", content=oversized)
    assert resp.status_code == 413
    body = resp.json()
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert body["error"]["request_id"]


def test_validation_422_and_unhandled_500_no_stack_trace(tmp_path: Path) -> None:
    settings = Settings(
        purvai_mode="local",
        database_path=str(tmp_path / "errors.db"),
        rate_limit_per_minute=1000,
    )
    app = create_app(settings)

    class ProbePayload(BaseModel):
        count: int

    @app.post("/api/v1/_test-validate")
    async def _probe_validate(payload: ProbePayload) -> dict[str, int]:
        return {"count": payload.count}

    @app.get("/api/v1/_test-boom")
    async def _probe_boom() -> None:
        raise RuntimeError("sensitive internal traceback detail")

    app.router.routes.insert(0, app.router.routes.pop())
    app.router.routes.insert(0, app.router.routes.pop())

    with TestClient(app, raise_server_exceptions=False) as client:
        r422 = client.post("/api/v1/_test-validate", json={"count": "not-an-int"})
        assert r422.status_code == 422
        assert r422.json()["error"]["code"] == "VALIDATION_ERROR"
        assert r422.json()["error"]["request_id"]

        r500 = client.get("/api/v1/_test-boom")
        assert r500.status_code == 500
        assert r500.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "Traceback" not in r500.text
        assert "sensitive internal traceback detail" not in r500.text


def test_rate_limit_429(tmp_path: Path) -> None:
    settings = Settings(
        purvai_mode="local",
        database_path=str(tmp_path / "ratelimit.db"),
        rate_limit_per_minute=2,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health").status_code == 200
        limited = client.get("/api/v1/health")
        assert limited.status_code == 429
        assert limited.headers.get("Retry-After") == "60"
        assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_chunked_body_without_content_length_returns_413(tmp_path: Path) -> None:
    """Chunked/streaming request without Content-Length exceeding 64 KB returns 413."""
    settings = Settings(
        purvai_mode="local",
        database_path=str(tmp_path / "chunked.db"),
        rate_limit_per_minute=1000,
    )
    app = create_app(settings)

    def _chunk_gen() -> object:
        for _ in range(70):
            yield b"x" * 1024

    with TestClient(app) as client:
        resp = client.post("/api/v1/health", content=_chunk_gen())  # type: ignore[arg-type]
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_trust_proxy_headers_controls_rate_limit_key(tmp_path: Path) -> None:
    """TRUST_PROXY_HEADERS=true keys rate limits on X-Forwarded-For first IP; false ignores it."""
    # false: both IPs share testclient address and hit limit on 3rd request
    app_false = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "proxy_false.db"),
            rate_limit_per_minute=2,
            trust_proxy_headers=False,
        )
    )
    with TestClient(app_false) as c_false:
        assert (
            c_false.get("/api/v1/health", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        )
        assert (
            c_false.get("/api/v1/health", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
        )
        assert (
            c_false.get("/api/v1/health", headers={"X-Forwarded-For": "3.3.3.3"}).status_code == 429
        )

    # true: distinct X-Forwarded-For IPs get independent buckets
    app_true = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "proxy_true.db"),
            rate_limit_per_minute=2,
            trust_proxy_headers=True,
        )
    )
    with TestClient(app_true) as c_true:
        assert (
            c_true.get("/api/v1/health", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        )
        assert (
            c_true.get("/api/v1/health", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
        )
        assert (
            c_true.get("/api/v1/health", headers={"X-Forwarded-For": "3.3.3.3"}).status_code == 200
        )
        assert (
            c_true.get("/api/v1/health", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        )
        assert (
            c_true.get("/api/v1/health", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
        )
