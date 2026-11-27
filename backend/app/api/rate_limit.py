"""Shared slowapi rate limiter and proxy-aware client IP key function (A11, A12)."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_rate_limit_key(request: Request) -> str:
    """Return client IP, honoring X-Forwarded-For first hop when TRUST_PROXY_HEADERS is true."""
    settings = getattr(request.app.state, "settings", None)
    if settings is not None and getattr(settings, "trust_proxy_headers", False):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first_ip = xff.split(",")[0].strip()
            if first_ip:
                return first_ip
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)
