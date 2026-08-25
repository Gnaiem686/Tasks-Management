from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from workforce_observability.metrics import MetricRegistry

api_metrics = MetricRegistry()

_WORKFLOWS = {
    "alerts": "alerts",
    "audit": "audit",
    "health": "health",
    "investigations": "investigation",
    "metrics": "metrics",
    "profiles": "profiles",
    "proposals": "proposal",
    "reports": "reports",
    "risks": "risk",
    "scans": "scan",
    "ui": "ui",
}


class ApiMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        status = response.status_code
        outcome = (
            "success"
            if status < 400
            else "client_error"
            if status < 500
            else "server_error"
        )
        segment = request.url.path.strip("/").split("/", maxsplit=2)[-1]
        workflow = _WORKFLOWS.get(segment, "other")
        api_metrics.increment(
            "workforce_http_requests_total",
            environment=request.app.state.environment,
            service="agent-api",
            workflow=workflow,
            outcome=outcome,
        )
        return response
