from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Set
from typing import Any, Protocol

from workforce_contracts.jira import JiraIssueEvidence

from jira_mcp_client.normalize import normalize_issue


class JiraProjectNotAllowed(PermissionError):
    pass


class JiraCircuitOpen(ConnectionError):
    pass


class JiraMcpTransport(Protocol):
    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, correlation_id: str
    ) -> Mapping[str, Any]: ...


class JiraEvidenceClient:
    def __init__(
        self,
        *,
        transport: JiraMcpTransport,
        environment: str,
        allowed_project_keys: Set[str],
        custom_fields: Mapping[str, str],
        timeout_seconds: float = 10.0,
        max_attempts: int = 2,
        circuit_failure_threshold: int = 3,
        circuit_reset_seconds: float = 30.0,
    ) -> None:
        self._transport = transport
        self._environment = environment
        self._allowed_projects = frozenset(allowed_project_keys)
        self._custom_fields = dict(custom_fields)
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_reset_seconds = circuit_reset_seconds
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None

    async def get_issue(
        self, issue_key: str, *, correlation_id: str
    ) -> JiraIssueEvidence:
        if self._circuit_opened_at is not None:
            elapsed = time.monotonic() - self._circuit_opened_at
            if elapsed < self._circuit_reset_seconds:
                raise JiraCircuitOpen("Jira MCP read circuit is open")
            self._circuit_opened_at = None
            self._consecutive_failures = 0
        project_key, separator, _ = issue_key.partition("-")
        if not separator or project_key not in self._allowed_projects:
            raise JiraProjectNotAllowed(f"Jira project is not allowed: {project_key}")
        fields = [
            "summary",
            "status",
            "priority",
            "assignee",
            "duedate",
            "timeoriginalestimate",
            "timeestimate",
            "updated",
            "issuelinks",
            "description",
            "comment",
            *self._custom_fields.values(),
        ]
        last_error: TimeoutError | None = None
        for attempt in range(self._max_attempts):
            try:
                raw = await asyncio.wait_for(
                    self._transport.call_tool(
                        "getJiraIssue",
                        {"issueIdOrKey": issue_key, "fields": fields},
                        correlation_id=correlation_id,
                    ),
                    timeout=self._timeout_seconds,
                )
                evidence = normalize_issue(
                    raw,
                    expected_environment=self._environment,
                    expected_correlation_id=correlation_id,
                    custom_fields=self._custom_fields,
                )
                self._consecutive_failures = 0
                return evidence
            except TimeoutError as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0)
        assert last_error is not None
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._circuit_failure_threshold:
            self._circuit_opened_at = time.monotonic()
        raise last_error
