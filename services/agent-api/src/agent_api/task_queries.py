from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from agent_api.graph.state import EntityReferences
from workforce_contracts.jira import JiraIssueEvidence


class TaskQueryKind(StrEnum):
    ISSUE_DUE_DATE = "issue_due_date"
    EMPLOYEE_DUE_BY = "employee_due_by"


class TaskQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: TaskQueryKind
    project_key: str
    issue_key: str | None = None
    employee_id: str | None = None
    due_by: date | None = None
    jql: str | None = None


class TaskFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    summary: str
    status: str
    due_date: date | None


class TaskQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    answer: str
    tasks: tuple[TaskFact, ...]
    evidence_references: tuple[str, ...]
    correlation_id: str


class JiraTaskReader(Protocol):
    async def get_issue(
        self, issue_key: str, *, correlation_id: str
    ) -> JiraIssueEvidence: ...

    async def search_issues(
        self, jql: str, *, project_key: str, correlation_id: str
    ) -> tuple[JiraIssueEvidence, ...]: ...


class JiraTaskQueryTool:
    def __init__(self, jira: JiraTaskReader, *, today: Callable[[], date]) -> None:
        self._jira = jira
        self._today = today

    async def query(
        self,
        question: str,
        references: EntityReferences,
        correlation_id: str,
    ) -> TaskQueryResult:
        query = parse_task_query(question, references, today=self._today())
        issues: tuple[JiraIssueEvidence, ...]
        if query.kind is TaskQueryKind.ISSUE_DUE_DATE:
            assert query.issue_key is not None
            issues = (
                await self._jira.get_issue(
                    query.issue_key, correlation_id=correlation_id
                ),
            )
            due = issues[0].due_date
            answer = (
                f"{issues[0].key} has no due date."
                if due is None
                else f"{issues[0].key} is due on {due.isoformat()}."
            )
        else:
            assert query.jql is not None and query.employee_id is not None
            assert query.due_by is not None
            issues = await self._jira.search_issues(
                query.jql,
                project_key=query.project_key,
                correlation_id=correlation_id,
            )
            issues = tuple(
                item
                for item in issues
                if item.workforce_employee_id == query.employee_id
            )
            task_labels = [
                f"{item.key} (due {item.due_date.isoformat()})"
                for item in issues
                if item.due_date is not None
            ]
            if not task_labels:
                listed = ""
            elif len(task_labels) == 1:
                listed = f": {task_labels[0]}"
            else:
                listed = f": {', '.join(task_labels[:-1])} and {task_labels[-1]}"
            employee_number = int(query.employee_id.removeprefix("EMP-"))
            answer = (
                f"Employee {employee_number} has {len(issues)} unfinished "
                f"{'task' if len(issues) == 1 else 'tasks'} due by "
                f"{query.due_by.isoformat()}{listed}."
            )
        facts = tuple(
            TaskFact(
                key=item.key,
                summary=item.summary,
                status=item.status,
                due_date=item.due_date,
            )
            for item in issues
        )
        citations = tuple(
            f"jira:{item.key}:duedate" for item in issues if item.due_date is not None
        )
        return TaskQueryResult(
            answer=answer,
            tasks=facts,
            evidence_references=citations,
            correlation_id=correlation_id,
        )


def parse_task_query(
    question: str, references: EntityReferences, *, today: date
) -> TaskQuery:
    issue_match = re.search(r"\b([A-Z][A-Z0-9]{1,19}-\d+)\b", question.upper())
    if issue_match and "due" in question.casefold():
        issue_key = issue_match.group(1)
        if not issue_key.startswith(f"{references.project_key}-"):
            raise ValueError("issue is outside the authorized project")
        return TaskQuery(
            kind=TaskQueryKind.ISSUE_DUE_DATE,
            project_key=references.project_key,
            issue_key=issue_key,
        )

    employee_match = re.search(r"\bemployee\s+(\d{1,3})\b", question.casefold())
    employee_id = references.employee_id
    if employee_match:
        number = int(employee_match.group(1))
        if number not in range(1, 8):
            raise ValueError("employee is outside the configured workforce")
        employee_id = f"EMP-{number:03d}"
    if employee_id is None:
        raise ValueError("employee is required for a deadline task query")
    if "tomorrow" not in question.casefold():
        raise ValueError("only an explicit tomorrow deadline is supported")
    due_by = today + timedelta(days=1)
    jql = (
        f'project = "{references.project_key}" '
        f'AND labels = "workforce-employee:{employee_id}" '
        'AND labels != "workforce-record:employee-profile" '
        f'AND duedate <= "{due_by.isoformat()}" '
        "AND statusCategory != Done ORDER BY duedate ASC, key ASC"
    )
    return TaskQuery(
        kind=TaskQueryKind.EMPLOYEE_DUE_BY,
        project_key=references.project_key,
        employee_id=employee_id,
        due_by=due_by,
        jql=jql,
    )
