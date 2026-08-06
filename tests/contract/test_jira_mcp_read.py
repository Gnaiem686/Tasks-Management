from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest
from jira_mcp_client.client import (
    JiraCircuitOpen,
    JiraEvidenceClient,
    JiraProjectNotAllowed,
)
from jira_mcp_client.transport import StreamableHttpJiraMcpTransport

FIXTURE = Path(__file__).parents[1] / "fixtures" / "jira" / "wrd_1_structured.json"


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, correlation_id: str
    ) -> dict[str, Any]:
        self.calls.append((name, arguments))
        response: dict[str, Any] = json.loads(FIXTURE.read_text())
        response["correlation_id"] = correlation_id
        return response


@pytest.mark.contract
@pytest.mark.asyncio
async def test_client_calls_get_jira_issue_and_returns_typed_evidence() -> None:
    transport = RecordingTransport()
    client = JiraEvidenceClient(
        transport=transport,
        environment="dev",
        allowed_project_keys={"WRD"},
        custom_fields={"blocker_category": "customfield_10042"},
    )

    result = await client.get_issue("WRD-1", correlation_id="corr-contract")

    assert result.key == "WRD-1"
    assert result.correlation_id == "corr-contract"
    assert transport.calls[0][0] == "getJiraIssue"
    assert transport.calls[0][1]["issueIdOrKey"] == "WRD-1"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_client_rejects_project_outside_allowlist_before_transport() -> None:
    transport = RecordingTransport()
    client = JiraEvidenceClient(
        transport=transport,
        environment="dev",
        allowed_project_keys={"WRD"},
        custom_fields={"blocker_category": "customfield_10042"},
    )

    with pytest.raises(JiraProjectNotAllowed):
        await client.get_issue("WORKFORCE-PROD-1", correlation_id="corr-contract")

    assert transport.calls == []


class TimingOutTransport:
    def __init__(self) -> None:
        self.attempts = 0

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, correlation_id: str
    ) -> dict[str, Any]:
        self.attempts += 1
        await asyncio.sleep(1)
        raise AssertionError("unreachable")


@pytest.mark.contract
@pytest.mark.asyncio
async def test_read_timeout_uses_bounded_retry_then_opens_circuit() -> None:
    transport = TimingOutTransport()
    client = JiraEvidenceClient(
        transport=transport,
        environment="dev",
        allowed_project_keys={"WRD"},
        custom_fields={"blocker_category": "customfield_10042"},
        timeout_seconds=0.001,
        max_attempts=2,
        circuit_failure_threshold=1,
    )

    with pytest.raises(TimeoutError):
        await client.get_issue("WRD-1", correlation_id="corr-timeout")
    with pytest.raises(JiraCircuitOpen):
        await client.get_issue("WRD-1", correlation_id="corr-open")

    assert transport.attempts == 2


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_dev_rovo_mcp_read_uses_real_streamable_http_transport() -> None:
    if os.getenv("RUN_LIVE_JIRA_MCP") != "1":
        pytest.skip("set RUN_LIVE_JIRA_MCP=1 for the credentialed dev smoke test")
    project = os.environ["JIRA_PROJECT_KEY"]
    if project != "WRD" or "PROD" in project.upper():
        pytest.fail("live Jira MCP contract test is restricted to synthetic WRD data")
    transport = StreamableHttpJiraMcpTransport(
        url=os.environ.get("JIRA_MCP_URL", "https://mcp.atlassian.com/v1/mcp"),
        cloud_id=os.environ["JIRA_CLOUD_ID"],
        environment="dev",
        authorization_header=os.environ["JIRA_MCP_AUTHORIZATION"],
    )
    client = JiraEvidenceClient(
        transport=transport,
        environment="dev",
        allowed_project_keys={project},
        custom_fields={
            "blocker_category": os.environ.get(
                "JIRA_BLOCKER_CATEGORY_FIELD_ID", "customfield_10042"
            )
        },
    )

    result = await client.get_issue("WRD-1", correlation_id="live-contract-wrd-1")

    assert result.key == "WRD-1"
    assert result.environment == "dev"
    assert result.correlation_id == "live-contract-wrd-1"
    assert result.custom_fields[0].logical_name == "blocker_category"
