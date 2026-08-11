from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Environment = Literal["dev", "prod", "test"]


class DiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    environment: Environment
    correlation_id: str = Field(min_length=1, max_length=128)


class DiagnosticEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    environment: Environment
    correlation_id: str
    evidence_timestamp: datetime
    status: Literal["success", "degraded", "error"]
    data: dict[str, Any]
    recommendations: tuple[str, ...] = ()


def envelope(
    request: DiagnosticRequest,
    *,
    data: dict[str, Any],
    status: Literal["success", "degraded", "error"] = "success",
    recommendations: tuple[str, ...] = (),
) -> DiagnosticEnvelope:
    return DiagnosticEnvelope(
        environment=request.environment,
        correlation_id=request.correlation_id,
        evidence_timestamp=datetime.now(UTC),
        status=status,
        data=data,
        recommendations=recommendations,
    )
