from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class MutationOutcome(StrEnum):
    EXECUTED_VERIFIED = "executed_verified"
    EXECUTION_FAILED = "execution_failed"
    UNCERTAIN = "uncertain"
    STALE = "stale"


class ReassignmentMutation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    environment: str
    project_key: str
    issue_key: str
    expected_assignee_id: str
    proposed_assignee_id: str
    proposal_id: str
    idempotency_key: str = Field(min_length=8)
    correlation_id: str


class MutationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: MutationOutcome
    observed_assignee_id: str | None = None
    edit_attempted: bool = False
    safe_error_code: str | None = None


class MutationTransport(Protocol):
    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, correlation_id: str
    ) -> Mapping[str, Any]: ...


def assignee_from_response(response: Mapping[str, Any]) -> str | None:
    data = response.get("data", response)
    if isinstance(data, Mapping) and isinstance(data.get("data"), Mapping):
        data = data["data"]
    fields = data.get("fields") if isinstance(data, Mapping) else None
    assignee = fields.get("assignee") if isinstance(fields, Mapping) else None
    value = assignee.get("accountId") if isinstance(assignee, Mapping) else None
    return value if isinstance(value, str) and value else None


class JiraAssigneeMutationClient:
    """Single-attempt Jira assignee mutation with mandatory fresh read-back."""

    def __init__(
        self,
        *,
        transport: MutationTransport,
        environment: str,
        allowed_project_keys: set[str],
    ) -> None:
        self._transport = transport
        self._environment = environment
        self._allowed_projects = frozenset(allowed_project_keys)

    async def read_assignee(self, issue_key: str, *, correlation_id: str) -> str | None:
        response = await self._transport.call_tool(
            "getJiraIssue",
            {"issueIdOrKey": issue_key, "fields": ["assignee"]},
            correlation_id=correlation_id,
        )
        return assignee_from_response(response)

    async def execute(self, command: ReassignmentMutation) -> MutationReceipt:
        issue_project, separator, _ = command.issue_key.partition("-")
        if (
            self._environment != "dev"
            or command.environment != self._environment
            or not separator
            or command.project_key != issue_project
            or command.project_key not in self._allowed_projects
        ):
            raise PermissionError(
                "Jira mutation is disabled for this environment or project"
            )

        try:
            current = await self.read_assignee(
                command.issue_key, correlation_id=command.correlation_id
            )
        except Exception:
            return MutationReceipt(
                outcome=MutationOutcome.EXECUTION_FAILED,
                safe_error_code="jira_precondition_read_failed",
            )
        if current != command.expected_assignee_id:
            return MutationReceipt(
                outcome=MutationOutcome.STALE, observed_assignee_id=current
            )

        try:
            edit_response = await self._transport.call_tool(
                "editJiraIssue",
                {
                    "issueIdOrKey": command.issue_key,
                    "fields": {"assignee": {"accountId": command.proposed_assignee_id}},
                },
                correlation_id=command.correlation_id,
            )
        except Exception:
            # Any write-side error is ambiguous. Never retry it here.
            return MutationReceipt(
                outcome=MutationOutcome.UNCERTAIN,
                edit_attempted=True,
                safe_error_code="jira_write_outcome_unknown",
            )
        if edit_response.get("status") == "error":
            return MutationReceipt(
                outcome=MutationOutcome.EXECUTION_FAILED,
                edit_attempted=True,
                safe_error_code="jira_write_rejected",
            )

        try:
            observed = await self.read_assignee(
                command.issue_key, correlation_id=command.correlation_id
            )
        except Exception:
            return MutationReceipt(
                outcome=MutationOutcome.UNCERTAIN,
                edit_attempted=True,
                safe_error_code="jira_verification_read_failed",
            )
        if observed == command.proposed_assignee_id:
            return MutationReceipt(
                outcome=MutationOutcome.EXECUTED_VERIFIED,
                observed_assignee_id=observed,
                edit_attempted=True,
            )
        return MutationReceipt(
            outcome=MutationOutcome.UNCERTAIN,
            observed_assignee_id=observed,
            edit_attempted=True,
            safe_error_code="jira_verification_mismatch",
        )
