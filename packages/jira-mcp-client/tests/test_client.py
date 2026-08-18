from datetime import UTC, datetime

import pytest
from jira_mcp_client.client import JiraEvidenceClient, JiraProjectNotAllowed


class Transport:
    arguments: dict[str, object] | None = None

    async def call_tool(
        self, name: str, arguments: dict[str, object], *, correlation_id: str
    ) -> dict[str, object]:
        self.arguments = arguments
        return {
            "schema_version": "1.0",
            "environment": "test",
            "correlation_id": correlation_id,
            "evidence_timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
            "data": {"issues": [], "total": 0},
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_requests_structured_work_situation_fields() -> None:
    transport = Transport()
    client = JiraEvidenceClient(
        transport=transport,
        environment="test",
        allowed_project_keys={"WRD"},
        custom_fields={"blocker_category": "customfield_10042"},
    )

    await client.search_issues(
        'project = "WRD" AND statusCategory != Done',
        project_key="WRD",
        correlation_id="corr-client",
    )

    assert transport.arguments is not None
    assert "timeestimate" in transport.arguments["fields"]
    assert "customfield_10042" in transport.arguments["fields"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_rejects_scope_broadening_or_expression() -> None:
    client = JiraEvidenceClient(
        transport=Transport(),
        environment="test",
        allowed_project_keys={"WRD"},
        custom_fields={},
    )

    with pytest.raises(JiraProjectNotAllowed):
        await client.search_issues(
            'project = "WRD" OR statusCategory != Done',
            project_key="WRD",
            correlation_id="corr-client",
        )
