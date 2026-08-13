from __future__ import annotations

from datetime import timedelta
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from scripts.jira.guards import validate_scenario_scope
from scripts.jira.scenario import OperationResult, ScenarioDefinition, ScenarioIssue


class ScenarioMcpTransport(Protocol):
    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        correlation_id: str,
    ) -> dict[str, Any]: ...


class ScenarioMcpResponseError(ValueError):
    pass


class McpVerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    valid: bool
    missing_external_ids: tuple[str, ...] = ()
    mismatched_external_ids: tuple[str, ...] = ()


class RovoScenarioSeeder:
    """Idempotent, MCP-only writer for the guarded WRD synthetic scenario."""

    def __init__(self, transport: ScenarioMcpTransport) -> None:
        self._transport = transport

    async def seed(
        self,
        scenario: ScenarioDefinition,
        *,
        correlation_id: str,
        blocker_field_id: str,
    ) -> OperationResult:
        validate_scenario_scope(
            environment=scenario.environment,
            project_key=scenario.project_key,
        )
        created = 0
        changed = 0
        issue_keys: dict[str, str] = {}
        existing_links: set[frozenset[str]] = set()
        for issue in scenario.issues:
            external_label = f"workforce-external:{issue.external_id}"
            search = await self._transport.call_tool(
                "searchJiraIssuesUsingJql",
                {
                    "jql": (
                        f'project = "{scenario.project_key}" '
                        f'AND labels = "{external_label}"'
                    ),
                    "fields": [
                        "key",
                        "labels",
                        "summary",
                        "duedate",
                        "issuelinks",
                        blocker_field_id,
                    ],
                    "maxResults": 50,
                },
                correlation_id=correlation_id,
            )
            matches = _issues(search)
            fields = _jira_fields(
                scenario,
                issue,
                blocker_field_id=blocker_field_id,
                external_label=external_label,
            )
            if not matches:
                response = await self._transport.call_tool(
                    "createJiraIssue",
                    {
                        "projectKey": scenario.project_key,
                        "issueTypeName": "Task",
                        "summary": issue.summary,
                        "description": (
                            "Synthetic work-planning fixture. All scoring inputs are "
                            "stored in structured Jira fields and labels."
                        ),
                        "additional_fields": fields,
                    },
                    correlation_id=correlation_id,
                )
                issue_keys[issue.external_id] = _issue_key(response)
                created += 1
            else:
                key = _issue_key(matches[0])
                issue_keys[issue.external_id] = key
                existing_links.update(linked_issue_pairs(matches[0]))
                await self._transport.call_tool(
                    "editJiraIssue",
                    {
                        "issueIdOrKey": key,
                        "fields": {"summary": issue.summary, **fields},
                    },
                    correlation_id=correlation_id,
                )
                changed += 1
        for issue in scenario.issues:
            for dependency in issue.dependencies:
                pair = frozenset(
                    {issue_keys[dependency], issue_keys[issue.external_id]}
                )
                if pair in existing_links:
                    continue
                await self._transport.call_tool(
                    "createIssueLink",
                    {
                        "type": "Blocks",
                        "inwardIssue": issue_keys[issue.external_id],
                        "outwardIssue": issue_keys[dependency],
                    },
                    correlation_id=correlation_id,
                )
                existing_links.add(pair)
        return OperationResult(created=created, changed=changed)


class RovoScenarioVerifier:
    def __init__(self, transport: ScenarioMcpTransport) -> None:
        self._transport = transport

    async def verify(
        self,
        scenario: ScenarioDefinition,
        *,
        correlation_id: str,
        blocker_field_id: str,
    ) -> McpVerificationResult:
        validate_scenario_scope(
            environment=scenario.environment,
            project_key=scenario.project_key,
        )
        missing: list[str] = []
        mismatched: list[str] = []
        for issue in scenario.issues:
            external_label = f"workforce-external:{issue.external_id}"
            response = await self._transport.call_tool(
                "searchJiraIssuesUsingJql",
                {
                    "jql": (
                        f'project = "{scenario.project_key}" '
                        f'AND labels = "{external_label}"'
                    ),
                    "fields": ["key", "labels", "summary", "duedate", blocker_field_id],
                    "maxResults": 50,
                },
                correlation_id=correlation_id,
            )
            matches = _issues(response)
            if len(matches) != 1:
                missing.append(issue.external_id)
                continue
            expected = _jira_fields(
                scenario,
                issue,
                blocker_field_id=blocker_field_id,
                external_label=external_label,
            )
            fields = matches[0].get("fields")
            if not isinstance(fields, dict):
                mismatched.append(issue.external_id)
                continue
            actual_labels = fields.get("labels")
            expected_labels = expected["labels"]
            if not isinstance(expected_labels, list):
                raise ScenarioMcpResponseError("expected labels must be a list")
            if not isinstance(actual_labels, list) or not set(
                str(label) for label in expected_labels
            ).issubset(actual_labels):
                mismatched.append(issue.external_id)
        return McpVerificationResult(
            valid=not missing and not mismatched,
            missing_external_ids=tuple(sorted(missing)),
            mismatched_external_ids=tuple(sorted(mismatched)),
        )


def _jira_fields(
    scenario: ScenarioDefinition,
    issue: ScenarioIssue,
    *,
    blocker_field_id: str,
    external_label: str,
) -> dict[str, object]:
    due_date = scenario.anchor_date + timedelta(days=issue.due_offset_days)
    priority = {
        "critical": "Highest",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }[issue.priority.casefold()]
    labels = [
        *issue.labels,
        external_label,
        f"workforce-estimate-hours:{issue.estimate_hours:g}",
        f"workforce-remaining-hours:{issue.remaining_hours:g}",
        f"workforce-difficulty:{issue.difficulty}",
        *(f"workforce-skill:{skill.casefold()}" for skill in issue.required_skills),
    ]
    if issue.senior_pairing_employee_id is not None:
        labels.append(f"workforce-senior-pair:{issue.senior_pairing_employee_id}")
    labels.append(
        "workforce-evidence:complete"
        if issue.evidence_complete
        else "workforce-evidence:incomplete"
    )
    if issue.workload_profile is not None:
        labels.append(f"workforce-workload-profile:{issue.workload_profile}")
    return {
        "labels": sorted(set(labels)),
        "priority": {"name": priority},
        "duedate": due_date.isoformat(),
        blocker_field_id: (
            {"value": issue.blocker_category}
            if issue.blocker_category is not None
            else None
        ),
    }


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise ScenarioMcpResponseError("MCP response data must be an object")
    return data


def _issues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _unwrap(payload).get("issues", [])
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ScenarioMcpResponseError("Jira search issues must be a list")
    return raw


def _issue_key(payload: dict[str, Any]) -> str:
    key = _unwrap(payload).get("key")
    if not isinstance(key, str) or not key.startswith("WRD-"):
        raise ScenarioMcpResponseError("Jira response is missing a WRD issue key")
    return key


def linked_issue_pairs(issue: dict[str, Any]) -> set[frozenset[str]]:
    current_key = issue.get("key")
    fields = issue.get("fields")
    if not isinstance(current_key, str) or not isinstance(fields, dict):
        return set()
    links = fields.get("issuelinks", [])
    if not isinstance(links, list):
        return set()
    result: set[frozenset[str]] = set()
    for link in links:
        if not isinstance(link, dict):
            continue
        link_type = link.get("type")
        if not isinstance(link_type, dict) or link_type.get("name") != "Blocks":
            continue
        other = link.get("inwardIssue", link.get("outwardIssue"))
        if isinstance(other, dict) and isinstance(other.get("key"), str):
            result.add(frozenset({current_key, other["key"]}))
    return result
