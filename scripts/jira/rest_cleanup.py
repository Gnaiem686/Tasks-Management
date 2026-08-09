from __future__ import annotations

from typing import Any, Protocol

import httpx

from scripts.jira.guards import ScenarioScopeError, validate_scenario_scope
from scripts.jira.scenario import OperationResult


class SearchTransport(Protocol):
    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        correlation_id: str,
    ) -> dict[str, Any]: ...


class IssueDeleteClient(Protocol):
    async def delete_issue(self, issue_key: str) -> None: ...


class JiraRestDeleteClient:
    def __init__(self, *, cloud_resource_id: str, authorization: str) -> None:
        self._base_url = (
            f"https://api.atlassian.com/ex/jira/{cloud_resource_id}/rest/api/3"
        )
        self._authorization = authorization

    async def delete_issue(self, issue_key: str) -> None:
        async with httpx.AsyncClient(
            headers={"Authorization": self._authorization}, timeout=15.0
        ) as client:
            response = await client.delete(f"{self._base_url}/issue/{issue_key}")
        if response.status_code != 204:
            raise RuntimeError(
                f"Jira cleanup failed safely with HTTP {response.status_code}"
            )


class GuardedRestCleanup:
    """Dev-only REST contingency because Rovo MCP has no delete operation."""

    def __init__(
        self, search_transport: SearchTransport, delete_client: IssueDeleteClient
    ) -> None:
        self._search = search_transport
        self._delete = delete_client

    async def cleanup(
        self,
        *,
        environment: str,
        project_key: str,
        ownership_tag: str,
        correlation_id: str,
    ) -> OperationResult:
        validate_scenario_scope(environment=environment, project_key=project_key)
        response = await self._search.call_tool(
            "searchJiraIssuesUsingJql",
            {
                "jql": f'project = "WRD" AND labels = "{ownership_tag}"',
                "fields": ["key", "labels"],
                "maxResults": 100,
            },
            correlation_id=correlation_id,
        )
        data = response.get("data", response)
        issues = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(issues, list):
            raise RuntimeError("Jira cleanup search returned an invalid response")
        keys: list[str] = []
        for issue in issues:
            if not isinstance(issue, dict):
                raise RuntimeError("Jira cleanup search returned an invalid issue")
            key = issue.get("key")
            fields = issue.get("fields")
            labels = fields.get("labels") if isinstance(fields, dict) else None
            if (
                not isinstance(key, str)
                or not key.startswith("WRD-")
                or not isinstance(labels, list)
                or ownership_tag not in labels
            ):
                raise ScenarioScopeError("cleanup search escaped WRD ownership scope")
            keys.append(key)
        for key in sorted(keys):
            await self._delete.delete_issue(key)
        return OperationResult(deleted=len(keys))
