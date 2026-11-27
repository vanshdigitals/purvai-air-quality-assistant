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
from starlette.types import ASGIApp

from app.api.errors import error_payload

MAX_BODY_BYTES = 64 * 1024  # 64 KB per docs/API.md and docs/SECURITY.md

CSP_HEADER = "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'"


def configure_json_logger(level_name: str) -> logging.Logger:
    """Configure stdout JSON logger for access and application events."""
    logger = logging.getLogger("purvai")
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    return logger


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request ID, enforce 64 KB body limit, log JSON access, and add security headers."""

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

        response: Response
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    response = self._too_large_response(request_id)
                    self._apply_headers(response, request_id)
                    self._log_access(request, response.status_code, start, request_id)
                    return response
            except ValueError:
                pass

        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            response = self._too_large_response(request_id)
            self._apply_headers(response, request_id)
            self._log_access(request, response.status_code, start, request_id)
            return response

        response = await call_next(request)
        self._apply_headers(response, request_id)
        self._log_access(request, response.status_code, start, request_id)
        return response

    @staticmethod
    def _too_large_response(request_id: str) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content=error_payload(
                "PAYLOAD_TOO_LARGE",
                "Request body exceeds 64 KB limit.",
                request_id,
            ),
        )

    def _apply_headers(self, response: Response, request_id: str) -> None:
        response.headers["X-Request-ID"] = request_id
        response.headers["Content-Security-Policy"] = CSP_HEADER
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
