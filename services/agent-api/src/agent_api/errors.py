from __future__ import annotations

from fastapi.responses import JSONResponse


def safe_error(
    *,
    status_code: int,
    error_code: str,
    message: str,
    correlation_id: str,
    degraded: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "correlation_id": correlation_id,
            "degraded": degraded,
        },
        headers={"X-Correlation-ID": correlation_id},
    )
