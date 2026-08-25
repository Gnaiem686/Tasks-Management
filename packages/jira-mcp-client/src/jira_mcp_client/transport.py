from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

from jira_mcp_client.normalize import JiraNormalizationError


def extract_issue_payload(result: CallToolResult) -> dict[str, Any]:
    if result.isError:
        raise JiraNormalizationError("Jira MCP tool returned an error")
    if result.structuredContent is not None:
        return dict(result.structuredContent)
    text_blocks = [
        block.text for block in result.content if isinstance(block, TextContent)
    ]
    if len(text_blocks) != 1:
        raise JiraNormalizationError(
            "Jira MCP result must contain exactly one JSON payload"
        )
    try:
        payload = json.loads(text_blocks[0])
    except json.JSONDecodeError as exc:
        raise JiraNormalizationError("Jira MCP returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise JiraNormalizationError("Jira MCP issue payload must be an object")
    return payload


class StreamableHttpJiraMcpTransport:
    """Official MCP SDK transport for Atlassian Rovo MCP."""

    def __init__(
        self,
        *,
        url: str,
        cloud_id: str,
        environment: str,
        authorization_header: str,
    ) -> None:
        self._url = url
        self._cloud_id = cloud_id
        self._environment = environment
        self._authorization_header = authorization_header

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, correlation_id: str
    ) -> dict[str, Any]:
        request_arguments = {"cloudId": self._cloud_id, **arguments}
        headers = {
            "Authorization": self._authorization_header,
            "X-Correlation-ID": correlation_id,
        }
        async with (
            httpx.AsyncClient(headers=headers, follow_redirects=False) as http_client,
            streamable_http_client(self._url, http_client=http_client) as (
                read_stream,
                write_stream,
                _,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            result = await session.call_tool(name, arguments=request_arguments)
        return {
            "schema_version": "1.0",
            "environment": self._environment,
            "correlation_id": correlation_id,
            "evidence_timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
            "data": extract_issue_payload(result),
        }
