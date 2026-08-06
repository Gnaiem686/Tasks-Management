from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from agent_api.auth.internal_context import InternalContextSigner
from agent_api.auth.principal import AuthenticatedPrincipal


class StreamableHttpProfileClient:
    def __init__(self, *, url: str, secret: bytes) -> None:
        self._url = url
        self._signer = InternalContextSigner(secret, lifetime=timedelta(seconds=60))

    async def update_capacity(
        self,
        *,
        employee_id: str,
        project_key: str,
        expected_version: int,
        weekly_capacity_hours: float,
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]:
        token = self._signer.sign(
            principal, correlation_id=correlation_id, now=datetime.now(UTC)
        )
        async with (
            httpx.AsyncClient(
                headers={"X-Workforce-Authorization": token}, timeout=10
            ) as http_client,
            streamable_http_client(self._url, http_client=http_client) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            response = await session.call_tool(
                "update_profile_capacity",
                arguments={
                    "request": {
                        "employee_id": employee_id,
                        "project_key": project_key,
                        "expected_version": expected_version,
                        "weekly_capacity_hours": weekly_capacity_hours,
                    }
                },
            )
        if response.isError:
            raise ValueError("Workforce MCP profile update failed")
        texts = [
            item.text for item in response.content if isinstance(item, TextContent)
        ]
        if len(texts) != 1:
            raise ValueError("Workforce MCP profile response is ambiguous")
        result = json.loads(texts[0])
        if not isinstance(result, dict):
            raise ValueError("Workforce MCP profile response is invalid")
        return result
