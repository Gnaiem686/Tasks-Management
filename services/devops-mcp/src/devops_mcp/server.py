from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from devops_mcp.backends import get_backend
from devops_mcp.tools.deployments import DeploymentRequest, inspect_deployment
from devops_mcp.tools.kubernetes import KubernetesRequest, inspect_workloads
from devops_mcp.tools.logs import LogRequest, read_logs
from devops_mcp.tools.prometheus import MetricRequest, query_metric
from devops_mcp.tools.queues import QueueRequest, inspect_queues

mcp = FastMCP(
    "Workforce DevOps MCP",
    host=os.getenv("DEVOPS_MCP_HOST", "127.0.0.1"),
    port=int(
        os.getenv("DEVOPS_MCP_LISTEN_PORT") or os.getenv("DEVOPS_MCP_PORT") or "8002"
    ),
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


def _validate_environment(environment: str) -> None:
    if environment != os.getenv("APP_ENVIRONMENT", "dev"):
        raise PermissionError("diagnostic environment mismatch")


@mcp.tool(name="inspect_kubernetes_workloads")
async def inspect_kubernetes_workloads(request: dict[str, Any]) -> dict[str, Any]:
    validated = KubernetesRequest.model_validate(request)
    _validate_environment(validated.environment)
    return (await inspect_workloads(validated, reader=get_backend())).model_dump(
        mode="json"
    )


@mcp.tool(name="query_health_metric")
async def query_health_metric(request: dict[str, Any]) -> dict[str, Any]:
    validated = MetricRequest.model_validate(request)
    _validate_environment(validated.environment)
    return (await query_metric(validated, reader=get_backend())).model_dump(mode="json")


@mcp.tool(name="read_service_logs")
async def read_service_logs(request: dict[str, Any]) -> dict[str, Any]:
    validated = LogRequest.model_validate(request)
    _validate_environment(validated.environment)
    return (await read_logs(validated, reader=get_backend())).model_dump(mode="json")


@mcp.tool(name="inspect_queue_health")
async def inspect_queue_health(request: dict[str, Any]) -> dict[str, Any]:
    validated = QueueRequest.model_validate(request)
    _validate_environment(validated.environment)
    return (await inspect_queues(validated, reader=get_backend())).model_dump(
        mode="json"
    )


@mcp.tool(name="inspect_deployment_health")
async def inspect_deployment_health(request: dict[str, Any]) -> dict[str, Any]:
    validated = DeploymentRequest.model_validate(request)
    _validate_environment(validated.environment)
    return (await inspect_deployment(validated, reader=get_backend())).model_dump(
        mode="json"
    )


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
