"""Security headers, request ID, body size limit, and structured access logging."""

import json
import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp

from app.api.errors import error_payload

MAX_BODY_BYTES = 64 * 1024  # 64 KB per docs/API.md and docs/SECURITY.md
MAX_IMPORT_BODY_BYTES = 5 * 1024 * 1024  # 5 MB for POST /api/v1/data/import

CSP_HEADER = (
    "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
    "style-src 'self'; frame-ancestors 'none'"
)


def configure_json_logger(level_name: str) -> logging.Logger:
    """Configure stdout JSON logger for access and application events."""
    logger = logging.getLogger("purvai")
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    if "pytest" not in sys.modules:
        logger.propagate = False
    return logger


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request ID, enforce body limits, log JSON access, and add security headers."""

    def __init__(self, app: ASGIApp, *, mode: str, logger: logging.Logger) -> None:
        super().__init__(app)
        self.mode = mode
        self.logger = logger

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_id = request.headers.get("X-Request-ID")
        request_id = (
            incoming_id.strip()[:64]
            if incoming_id and incoming_id.strip()
            else f"r-{uuid.uuid4().hex[:8]}"
        )
        request.state.request_id = request_id
        start = time.perf_counter()

        limit = (
            MAX_IMPORT_BODY_BYTES if request.url.path == "/api/v1/data/import" else MAX_BODY_BYTES
        )

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    return self._reject_too_large(request, limit, start, request_id)
            except ValueError:
                pass

        # Stream chunks to enforce limit even on chunked requests without Content-Length
        chunks: list[bytes] = []
        total = 0
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > limit:
                    return self._reject_too_large(request, limit, start, request_id)
                chunks.append(chunk)
        except ClientDisconnect:
            return Response(status_code=499)

        request._body = b"".join(chunks)

        response = await call_next(request)
        self._apply_headers(response, request_id)
        self._log_access(request, response.status_code, start, request_id)
        return response

    def _reject_too_large(
        self,
        request: Request,
        limit: int,
        start: float,
        request_id: str,
    ) -> JSONResponse:
        label = "5 MB" if limit == MAX_IMPORT_BODY_BYTES else "64 KB"
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content=error_payload(
                "PAYLOAD_TOO_LARGE",
                f"Request body exceeds {label} limit.",
                request_id,
            ),
        )
        self._apply_headers(response, request_id)
        self._log_access(request, response.status_code, start, request_id)
        return response

    def _apply_headers(self, response: Response, request_id: str) -> None:
        response.headers["X-Request-ID"] = request_id
        response.headers["Content-Security-Policy"] = CSP_HEADER
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self)"
        if self.mode == "demo":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    def _log_access(
        self, request: Request, status_code: int, start: float, request_id: str
    ) -> None:
        duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
        payload = {
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status": status_code,
            "duration_ms": duration_ms,
            "request_id": request_id,
        }
        self.logger.info(json.dumps(payload))
