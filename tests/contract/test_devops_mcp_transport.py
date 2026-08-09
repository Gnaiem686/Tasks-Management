from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from tests.integration.processes import (
    ProcessGroup,
    allocate_port,
    start_python_process,
)

ROOT = Path(__file__).parents[2]


@pytest.mark.contract
def test_real_streamable_http_lists_only_read_tools_and_returns_evidence() -> None:
    async def exercise(port: int) -> None:
        async with (
            streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {
                "inspect_kubernetes_workloads",
                "query_health_metric",
                "read_service_logs",
                "inspect_queue_health",
                "inspect_deployment_health",
            }
            forbidden_actions = {
                "restart",
                "scale",
                "deploy",
                "rollback",
                "delete",
                "update",
            }
            assert all(
                name.split("_", maxsplit=1)[0] not in forbidden_actions
                for name in names
            )
            result = await session.call_tool(
                "query_health_metric",
                arguments={
                    "request": {
                        "schema_version": "1.0",
                        "environment": "test",
                        "correlation_id": "corr-real-devops",
                        "query_name": "scan_freshness",
                    }
                },
            )
            assert result.isError is False
            texts = [
                block.text for block in result.content if isinstance(block, TextContent)
            ]
            payload = json.loads(texts[0])
            assert payload["schema_version"] == "1.0"
            assert payload["correlation_id"] == "corr-real-devops"

    port = allocate_port()
    with ProcessGroup() as processes:
        processes.add(
            start_python_process(
                name="devops-mcp",
                port=port,
                module="devops_mcp.server",
                root=ROOT,
                environment={
                    "DEVOPS_MCP_HOST": "127.0.0.1",
                    "DEVOPS_MCP_PORT": str(port),
                    "APP_ENVIRONMENT": "test",
                    "DEVOPS_BACKEND_MODE": "fixture",
                },
            )
        )
        asyncio.run(exercise(port))


@pytest.mark.contract
@pytest.mark.asyncio
async def test_transport_connection_failure_is_clear() -> None:
    port = allocate_port()
    with pytest.raises((httpx.ConnectError, ExceptionGroup)):
        async with (
            streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
