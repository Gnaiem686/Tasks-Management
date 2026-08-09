from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from devops_mcp.schemas import DiagnosticEnvelope, DiagnosticRequest, envelope

SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+\S+|api[_-]?key\s*[=:]\s*\S+|password\s*[=:]\s*\S+)"
)
ALLOWED_SERVICES = {
    "agent-api",
    "workforce-risk-mcp",
    "devops-mcp",
    "notification-worker",
}


class LogRequest(DiagnosticRequest):
    model_config = ConfigDict(extra="forbid")
    service: str
    start: AwareDatetime
    end: AwareDatetime
    limit: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def validate_window(self) -> LogRequest:
        if self.service not in ALLOWED_SERVICES:
            raise ValueError("service is not allowlisted")
        if self.end <= self.start or self.end - self.start > timedelta(hours=1):
            raise ValueError("log window must be positive and at most one hour")
        return self


class LogReader(Protocol):
    async def read(
        self,
        *,
        service: str,
        namespace: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[str]: ...


async def read_logs(request: LogRequest, *, reader: LogReader) -> DiagnosticEnvelope:
    lines = await reader.read(
        service=request.service,
        namespace=request.environment,
        start=request.start,
        end=request.end,
        limit=request.limit,
    )
    redacted = [
        SECRET_PATTERN.sub("<redacted>", line)[:2_000]
        for line in lines[: request.limit]
    ]
    return envelope(
        request,
        data={"service": request.service, "lines": redacted, "returned": len(redacted)},
    )
