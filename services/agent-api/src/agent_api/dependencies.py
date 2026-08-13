from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from jira_mcp_client.client import JiraEvidenceClient
from jira_mcp_client.transport import StreamableHttpJiraMcpTransport
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from pydantic import BaseModel, ConfigDict
from workforce_contracts.jira import JiraIssueEvidence
from workforce_risk.models import EmployeeOverloadInput, RiskResult


class JiraEvidenceTimeout(TimeoutError):
    pass


class WorkforceMcpInvalidResponse(ValueError):
    pass


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input: EmployeeOverloadInput
    degraded: bool = False
    missing_sources: tuple[str, ...] = ()


class EmployeeEvidenceProvider(Protocol):
    async def get_employee_overload(
        self, employee_id: str, project_key: str, correlation_id: str
    ) -> EvidenceBundle: ...


class JiraIssueReader(Protocol):
    async def get_issue(
        self, issue_key: str, *, correlation_id: str
    ) -> JiraIssueEvidence: ...


class WorkforceScoringClient(Protocol):
    async def score(
        self, input_data: EmployeeOverloadInput, correlation_id: str
    ) -> dict[str, Any]: ...


class FixtureEvidenceProvider:
    """Credential-free synthetic evidence provider restricted to non-production."""

    def __init__(
        self,
        fixture_directory: Path,
        environment: Literal["dev", "prod", "test"],
    ) -> None:
        if environment == "prod":
            raise RuntimeError("fixture evidence mode is forbidden in production")
        self._fixture_directory = fixture_directory

    async def get_employee_overload(
        self, employee_id: str, project_key: str, correlation_id: str
    ) -> EvidenceBundle:
        path = self._fixture_directory / (
            "overloaded_employee.json"
            if employee_id == "EMP-002"
            else "balanced_team.json"
        )
        input_data = EmployeeOverloadInput.model_validate_json(path.read_text())
        return EvidenceBundle(
            input=input_data.model_copy(
                update={
                    "employee_id": employee_id,
                    "evidence_timestamp": datetime.now(UTC),
                }
            )
        )


class SingleIssueJiraEvidenceProvider:
    """First vertical slice: convert one configured Jira issue into score input."""

    def __init__(
        self,
        *,
        jira_client: JiraIssueReader,
        employee_issue_keys: dict[str, str],
        employee_capacity_hours: dict[str, float],
        environment: Literal["dev", "prod", "test"],
    ) -> None:
        self._jira = jira_client
        self._issue_keys = employee_issue_keys
        self._capacity = employee_capacity_hours
        self._environment = environment

    async def get_employee_overload(
        self, employee_id: str, project_key: str, correlation_id: str
    ) -> EvidenceBundle:
        try:
            issue_key = self._issue_keys[employee_id]
            capacity = self._capacity[employee_id]
        except KeyError as exc:
            raise ValueError("employee Jira mapping is not configured") from exc
        if not issue_key.startswith(f"{project_key}-"):
            raise ValueError("employee issue is outside the requested project")
        try:
            issue = await self._jira.get_issue(issue_key, correlation_id=correlation_id)
        except TimeoutError as exc:
            raise JiraEvidenceTimeout("Jira MCP read timed out") from exc

        observed = issue.evidence_timestamp
        blocker = next(
            (
                field.value
                for field in issue.custom_fields
                if field.logical_name == "blocker_category"
            ),
            None,
        )
        remaining_hours = (
            issue.remaining_estimate_seconds / 3600
            if issue.remaining_estimate_seconds is not None
            else None
        )
        now = datetime.now(UTC)
        workload = {
            None: (1, 1, 1, 1, 1, 1, 0),
            "balanced": (0, 0, 0, 0, 1, 1, 0),
            "stalled": (0, 0, 1, 1, 4, 2, 1),
            "high": (2, 2, 3, 3, 8, 3, 2),
            "critical": (4, 3, 4, 4, 10, 4, 3),
            "recovery": (0, 0, 0, 1, 2, 1, 0),
        }[issue.workload_profile]
        (
            overdue_count,
            blocked_count,
            priority_count,
            due_count,
            active_count,
            project_count,
            stale_count,
        ) = workload
        overdue = int(
            issue.due_date is not None
            and issue.due_date < now.date()
            and issue.status.lower() not in {"done", "closed", "resolved"}
        )
        due_soon = int(
            issue.due_date is not None
            and now.date() <= issue.due_date <= (now + timedelta(days=7)).date()
        )
        references = tuple(
            f"jira:{reference.issue_key}:{reference.field_id}"
            for reference in issue.evidence_references
        )
        factor_references = {
            name: references
            for name in (
                "utilization",
                "overdue_work",
                "blocked_work",
                "priority_load",
                "due_soon_load",
                "active_task_count",
                "concurrent_projects",
                "stale_work",
            )
        }
        return EvidenceBundle(
            input=EmployeeOverloadInput(
                employee_id=employee_id,
                environment=self._environment,
                remaining_estimated_hours=remaining_hours,
                available_capacity_hours=capacity,
                overdue_tasks=max(overdue, overdue_count),
                blocked_or_blocking_tasks=max(
                    int(blocker not in {None, "", "None"}), blocked_count
                ),
                urgent_high_priority_tasks=max(
                    priority_count,
                    int(
                        issue.priority is not None
                        and issue.priority.lower() in {"high", "highest", "urgent"}
                    ),
                ),
                due_soon_tasks=max(due_soon, due_count),
                active_tasks=active_count,
                concurrent_projects=project_count,
                stale_tasks=max(
                    int((now - issue.activity_timestamp).days >= 7), stale_count
                ),
                evidence_timestamp=observed,
                evidence_references=factor_references,
            )
        )


class StreamableHttpWorkforceScoringClient:
    def __init__(self, url: str, environment: str, timeout_seconds: float = 10) -> None:
        self._url = url
        self._environment = environment
        self._timeout_seconds = timeout_seconds

    async def score(
        self, input_data: EmployeeOverloadInput, correlation_id: str
    ) -> dict[str, Any]:
        scored_at = datetime.now(UTC)
        arguments = {
            "request": {
                "schema_version": "1.0",
                "environment": self._environment,
                "correlation_id": correlation_id,
                "deadline_at": (
                    scored_at + timedelta(seconds=self._timeout_seconds)
                ).isoformat(),
                "scored_at": scored_at.isoformat(),
                "input": input_data.model_dump(mode="json"),
            }
        }
        async with (
            streamable_http_client(self._url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            response = await session.call_tool(
                "score_employee_overload", arguments=arguments
            )
        if response.isError:
            raise WorkforceMcpInvalidResponse("Workforce MCP tool failed")
        text = [
            block.text for block in response.content if isinstance(block, TextContent)
        ]
        if len(text) != 1:
            raise WorkforceMcpInvalidResponse("Workforce MCP response is ambiguous")
        try:
            envelope = json.loads(text[0])
            if (
                envelope["schema_version"] != "1.0"
                or envelope["environment"] != self._environment
                or envelope["correlation_id"] != correlation_id
                or envelope["status"] != "success"
            ):
                raise WorkforceMcpInvalidResponse("Workforce MCP envelope mismatch")
            result = RiskResult.model_validate(envelope["result"])
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise WorkforceMcpInvalidResponse(
                "Workforce MCP response is invalid"
            ) from exc
        return result.model_dump(mode="json")


def get_evidence_provider() -> EmployeeEvidenceProvider:
    mode = os.getenv("EVIDENCE_MODE", "jira")
    raw_environment = os.getenv("APP_ENVIRONMENT", "dev")
    if raw_environment not in {"dev", "prod", "test"}:
        raise RuntimeError("APP_ENVIRONMENT must be dev, prod, or test")
    environment = cast(Literal["dev", "prod", "test"], raw_environment)
    if mode == "fixture":
        directory = Path(os.getenv("EVIDENCE_FIXTURE_DIR", "tests/fixtures/scenarios"))
        return FixtureEvidenceProvider(directory, environment)
    if mode != "jira":
        raise RuntimeError("unknown evidence provider mode")
    required = {
        name: os.environ.get(name)
        for name in (
            "JIRA_MCP_AUTHORIZATION",
            "JIRA_CLOUD_ID",
            "JIRA_EMPLOYEE_ISSUE_MAP",
            "WORKFORCE_CAPACITY_MAP",
        )
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"missing Jira evidence configuration: {', '.join(missing)}")
    transport = StreamableHttpJiraMcpTransport(
        url=os.getenv("JIRA_MCP_URL", "https://mcp.atlassian.com/v1/mcp"),
        cloud_id=str(required["JIRA_CLOUD_ID"]),
        environment=environment,
        authorization_header=str(required["JIRA_MCP_AUTHORIZATION"]),
    )
    project = os.getenv("JIRA_PROJECT_KEY", "WRD")
    jira = JiraEvidenceClient(
        transport=transport,
        environment=environment,
        allowed_project_keys={project},
        custom_fields={
            "blocker_category": os.getenv(
                "JIRA_BLOCKER_CATEGORY_FIELD_ID", "customfield_10042"
            )
        },
    )
    return SingleIssueJiraEvidenceProvider(
        jira_client=jira,
        employee_issue_keys=json.loads(str(required["JIRA_EMPLOYEE_ISSUE_MAP"])),
        employee_capacity_hours=json.loads(str(required["WORKFORCE_CAPACITY_MAP"])),
        environment=environment,
    )


def get_scoring_client() -> WorkforceScoringClient:
    return StreamableHttpWorkforceScoringClient(
        os.getenv("WORKFORCE_MCP_URL", "http://127.0.0.1:8001/mcp"),
        os.getenv("APP_ENVIRONMENT", "dev"),
    )
