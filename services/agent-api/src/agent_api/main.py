from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from agent_api.observability import ApiMetricsMiddleware, api_metrics
from agent_api.routes.alerts import router as alert_router
from agent_api.routes.audit import router as audit_router
from agent_api.routes.investigations import router as investigation_router
from agent_api.routes.profiles import router as profile_router
from agent_api.routes.proposals import router as proposal_router
from agent_api.routes.reports import router as report_router
from agent_api.routes.risks import router as risk_router
from agent_api.routes.scans import router as scan_router
from agent_api.routes.ui import router as ui_router
from agent_api.security.limits import RequestBoundaryMiddleware

app = FastAPI(title="Workforce Risk Agent API", version="0.1.0")
app.state.environment = os.getenv("APP_ENVIRONMENT", "dev")
app.add_middleware(ApiMetricsMiddleware)
app.add_middleware(RequestBoundaryMiddleware)
app.include_router(risk_router)
app.include_router(profile_router)
app.include_router(proposal_router)
app.include_router(investigation_router)
app.include_router(scan_router)
app.include_router(alert_router)
app.include_router(report_router)
app.include_router(audit_router)
app.include_router(ui_router)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "web" / "static"),
    name="static",
)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", "corr-unassigned")
    codes = {
        401: "AUTHENTICATION_REQUIRED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        413: "REQUEST_TOO_LARGE",
        428: "PRECONDITION_REQUIRED",
        429: "RATE_LIMITED",
        503: "SERVICE_UNAVAILABLE",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": codes.get(exc.status_code, "REQUEST_REJECTED"),
            "message": str(exc.detail),
            "correlation_id": correlation_id,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", "corr-unassigned")
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_FAILED",
            "message": "Request validation failed.",
            "correlation_id": correlation_id,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "live"}


@app.get("/health/startup")
async def startup() -> dict[str, str]:
    return {"status": "started"}


@app.get("/health/ready")
async def readiness() -> dict[str, str]:
    # Dependency-specific failures are handled at each workflow boundary. This
    # endpoint means the API can safely accept and classify a request.
    return {"status": "ready", "mode": "request-specific"}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(
        api_metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8"
    )
