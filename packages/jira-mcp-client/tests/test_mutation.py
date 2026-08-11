from __future__ import annotations

from typing import Any

import pytest
from jira_mcp_client.mutation import (
    JiraAssigneeMutationClient,
    MutationOutcome,
    ReassignmentMutation,
)


class FakeTransport:
    def __init__(self, responses: list[dict[str, Any] | BaseException]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, correlation_id: str
    ) -> dict[str, Any]:
        self.calls.append((name, arguments, correlation_id))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def issue(assignee: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "environment": "dev",
        "correlation_id": "corr-1",
        "status": "success",
        "data": {"fields": {"assignee": {"accountId": assignee}}},
    }


def command(**changes: str) -> ReassignmentMutation:
    values = {
        "environment": "dev",
        "project_key": "WRD",
        "issue_key": "WRD-1",
        "expected_assignee_id": "old-account",
        "proposed_assignee_id": "new-account",
        "proposal_id": "proposal-1",
        "idempotency_key": "execute-123",
        "correlation_id": "corr-1",
    }
    values.update(changes)
    return ReassignmentMutation(**values)


@pytest.mark.asyncio
async def test_exact_assignee_payload_and_verified_readback() -> None:
    transport = FakeTransport(
        [issue("old-account"), {"status": "success"}, issue("new-account")]
    )
    client = JiraAssigneeMutationClient(
        transport=transport, environment="dev", allowed_project_keys={"WRD"}
    )

    result = await client.execute(command())

    assert result.outcome is MutationOutcome.EXECUTED_VERIFIED
    assert [call[0] for call in transport.calls] == [
        "getJiraIssue",
        "editJiraIssue",
        "getJiraIssue",
    ]
    assert transport.calls[1][1] == {
        "issueIdOrKey": "WRD-1",
        "fields": {"assignee": {"accountId": "new-account"}},
    }


@pytest.mark.asyncio
async def test_expected_assignee_mismatch_is_stale_without_write() -> None:
    transport = FakeTransport([issue("someone-else")])
    client = JiraAssigneeMutationClient(
        transport=transport, environment="dev", allowed_project_keys={"WRD"}
    )
    result = await client.execute(command())
    assert result.outcome is MutationOutcome.STALE
    assert [call[0] for call in transport.calls] == ["getJiraIssue"]


@pytest.mark.asyncio
async def test_write_timeout_is_uncertain_and_never_retried() -> None:
    transport = FakeTransport([issue("old-account"), TimeoutError("ambiguous")])
    client = JiraAssigneeMutationClient(
        transport=transport, environment="dev", allowed_project_keys={"WRD"}
    )
    result = await client.execute(command())
    assert result.outcome is MutationOutcome.UNCERTAIN
    assert [call[0] for call in transport.calls].count("editJiraIssue") == 1


@pytest.mark.asyncio
async def test_explicit_write_rejection_is_failed_without_readback() -> None:
    transport = FakeTransport([issue("old-account"), {"status": "error"}])
    client = JiraAssigneeMutationClient(
        transport=transport, environment="dev", allowed_project_keys={"WRD"}
    )
    result = await client.execute(command())
    assert result.outcome is MutationOutcome.EXECUTION_FAILED
    assert [call[0] for call in transport.calls] == ["getJiraIssue", "editJiraIssue"]


@pytest.mark.asyncio
async def test_mismatched_readback_is_uncertain() -> None:
    transport = FakeTransport(
        [issue("old-account"), {"status": "success"}, issue("third-account")]
    )
    client = JiraAssigneeMutationClient(
        transport=transport, environment="dev", allowed_project_keys={"WRD"}
    )
    result = await client.execute(command())
    assert result.outcome is MutationOutcome.UNCERTAIN


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "project"), [("prod", "WRD"), ("dev", "OTHER")]
)
async def test_mutation_is_impossible_for_prod_or_forbidden_project(
    environment: str, project: str
) -> None:
    transport = FakeTransport([])
    client = JiraAssigneeMutationClient(
        transport=transport, environment=environment, allowed_project_keys={"WRD"}
    )
    with pytest.raises(PermissionError):
        await client.execute(
            command(
                environment=environment, project_key=project, issue_key=f"{project}-1"
            )
        )
    assert transport.calls == []
