from __future__ import annotations

from typing import Protocol

from pydantic import ConfigDict

from devops_mcp.schemas import DiagnosticEnvelope, DiagnosticRequest, envelope


class QueueRequest(DiagnosticRequest):
    model_config = ConfigDict(extra="forbid")


class QueueReader(Protocol):
    async def attributes(self, environment: str) -> dict[str, int]: ...


async def inspect_queues(
    request: QueueRequest, *, reader: QueueReader
) -> DiagnosticEnvelope:
    attributes = await reader.attributes(request.environment)
    allowed = {
        key: int(attributes.get(key, 0))
        for key in ("visible", "in_flight", "oldest_age_seconds", "dlq_visible")
    }
    degraded = allowed["dlq_visible"] > 0 or allowed["oldest_age_seconds"] > 120
    return envelope(
        request,
        data=allowed,
        status="degraded" if degraded else "success",
        recommendations=("Inspect notification worker failures and DLQ messages.",)
        if degraded
        else (),
    )
