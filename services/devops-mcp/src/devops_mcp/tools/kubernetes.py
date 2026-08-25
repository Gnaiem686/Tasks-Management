from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import ConfigDict

from devops_mcp.schemas import DiagnosticEnvelope, DiagnosticRequest, envelope


class KubernetesRequest(DiagnosticRequest):
    model_config = ConfigDict(extra="forbid")
    resource: Literal["pods", "deployments"]


class KubernetesReader(Protocol):
    async def list(self, resource: str, namespace: str) -> list[dict[str, Any]]: ...


async def inspect_workloads(
    request: KubernetesRequest, *, reader: KubernetesReader
) -> DiagnosticEnvelope:
    namespace = request.environment
    records = await reader.list(request.resource, namespace)
    safe = [
        {
            key: record.get(key)
            for key in ("name", "namespace", "ready", "status", "restarts", "replicas")
        }
        for record in records
    ]
    if any(item.get("namespace") != namespace for item in safe):
        raise PermissionError("Kubernetes response crossed namespace scope")
    unhealthy = sum(not bool(item.get("ready")) for item in safe)
    return envelope(
        request,
        data={"resource": request.resource, "items": safe, "unhealthy": unhealthy},
        status="degraded" if unhealthy else "success",
        recommendations=("Inspect workload events and recent logs.",)
        if unhealthy
        else (),
    )
