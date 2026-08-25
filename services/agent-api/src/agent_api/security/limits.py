from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


@dataclass(frozen=True)
class RouteLimit:
    requests: int
    window_seconds: int
    max_body_bytes: int


POLICIES = {
    "investigations": RouteLimit(20, 60, 16_384),
    "scans": RouteLimit(3, 60, 8_192),
    "simulations": RouteLimit(20, 60, 16_384),
    "proposals": RouteLimit(10, 60, 16_384),
    "reports": RouteLimit(30, 60, 4_096),
    "default": RouteLimit(120, 60, 65_536),
}


def route_group(path: str) -> str:
    for group in ("investigations", "scans", "simulations", "proposals", "reports"):
        if f"/{group}" in path:
            return group
    return "default"


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}

    def reset(self) -> None:
        self._windows.clear()

    def allow(self, key: str, policy: RouteLimit, now: float) -> bool:
        if len(self._windows) > 10_000:
            self._windows = {
                item_key: value
                for item_key, value in self._windows.items()
                if now - value[0] < 60
            }
        started, count = self._windows.get(key, (now, 0))
        if now - started >= policy.window_seconds:
            started, count = now, 0
        if count >= policy.requests:
            return False
        self._windows[key] = (started, count + 1)
        return True


limiter = InMemoryRateLimiter()


class RequestBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        group = route_group(request.url.path)
        policy = POLICIES[group]
        correlation_id = request.headers.get("X-Correlation-ID", f"corr-{uuid4()}")
        request.state.correlation_id = correlation_id
        length = request.headers.get("content-length")
        if length is not None:
            try:
                declared_length = int(length)
            except ValueError:
                return self._error(400, "INVALID_CONTENT_LENGTH", correlation_id)
            if declared_length > policy.max_body_bytes:
                return self._error(413, "REQUEST_TOO_LARGE", correlation_id)
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > policy.max_body_bytes:
                return self._error(413, "REQUEST_TOO_LARGE", correlation_id)
        authorization = request.headers.get("authorization", "anonymous")
        identity = hashlib.sha256(authorization.encode()).hexdigest()[:24]
        key = f"{group}:{request.method}:{identity}"
        if not limiter.allow(key, policy, time.monotonic()):
            return self._error(429, "RATE_LIMITED", correlation_id)
        response = await call_next(request)
        response.headers.setdefault("X-Correlation-ID", correlation_id)
        return response

    @staticmethod
    def _error(status: int, code: str, correlation_id: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"error_code": code, "correlation_id": correlation_id},
            headers={"X-Correlation-ID": correlation_id},
        )
