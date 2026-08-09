from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import ConfigDict

from devops_mcp.schemas import DiagnosticEnvelope, DiagnosticRequest, envelope


class DeploymentRequest(DiagnosticRequest):
    model_config = ConfigDict(extra="forbid")
    source: Literal["github_actions", "release_metadata", "jira_integration"]


class DeploymentReader(Protocol):
    async def inspect(self, source: str, environment: str) -> dict[str, Any]: ...


async def inspect_deployment(
    request: DeploymentRequest, *, reader: DeploymentReader
) -> DiagnosticEnvelope:
    raw = await reader.inspect(request.source, request.environment)
    allowed_keys = {
        "github_actions": ("workflow", "conclusion", "commit", "completed_at"),
        "release_metadata": (
            "commit",
            "image_digests",
            "migration_version",
            "deployed_at",
        ),
        "jira_integration": (
            "availability",
            "latency_ms",
            "auth_failures",
            "jql_failures",
            "schema_failures",
            "rate_limits",
            "conflicts",
            "verification_failures",
            "circuit_open",
        ),
    }[request.source]
    data = {key: raw.get(key) for key in allowed_keys}
    degraded = (
        any(
            bool(data.get(key))
            for key in (
                "auth_failures",
                "jql_failures",
                "schema_failures",
                "rate_limits",
                "conflicts",
                "verification_failures",
                "circuit_open",
            )
        )
        or data.get("conclusion") == "failure"
    )
    return envelope(
        request,
        data=data,
        status="degraded" if degraded else "success",
        recommendations=("Follow the linked integration or deployment runbook.",)
        if degraded
        else (),
    )
