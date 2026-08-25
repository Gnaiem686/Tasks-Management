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
    ISSUE_STATUS = "issue_status"
    ISSUE_ASSIGNEE = "issue_assignee"
    REFERENCED_TASK_ASSIGNEE = "referenced_task_assignee"
    EMPLOYEE_DUE_BY = "employee_due_by"
    DONE_TASKS = "list_done_tasks"
    MISSING_ESTIMATES = "missing_estimates"
    BLOCKED_TASKS = "blocked_tasks"
    OVERDUE_TASKS = "overdue_tasks"
    DUE_SOON_TASKS = "due_soon_tasks"
    AMBIGUOUS_REFERENT = "ambiguous_referent"


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
    assignee: str | None = None
    due_date: date | None = None
    remaining_hours: float | None = None
    blocker: str | None = None
    dependencies: tuple[str, ...] = ()


class GroundedAnswerContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    intent: str
    previous_question: str | None = None
    issues: tuple[TaskFact, ...] = ()
    employee_ids: tuple[str, ...] = ()
    exhaustive: bool = False


class TaskQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    answer: str
    tasks: tuple[TaskFact, ...]
    evidence_references: tuple[str, ...]
    correlation_id: str
    context: GroundedAnswerContext | None = None


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
        *,
        previous_context: GroundedAnswerContext | None = None,
    ) -> TaskQueryResult:
        query = parse_task_query(
            question,
            references,
            today=self._today(),
            previous_context=previous_context,
        )
        issues: tuple[JiraIssueEvidence, ...]
        if query.kind is TaskQueryKind.AMBIGUOUS_REFERENT:
            assert previous_context is not None
            keys = [item.key for item in previous_context.issues]
            answer = f"Which task do you mean: {', '.join(keys[:-1])} or {keys[-1]}?"
            issues = ()
        elif query.kind in {
            TaskQueryKind.ISSUE_DUE_DATE,
            TaskQueryKind.ISSUE_STATUS,
            TaskQueryKind.ISSUE_ASSIGNEE,
            TaskQueryKind.REFERENCED_TASK_ASSIGNEE,
        }:
            assert query.issue_key is not None
            issues = (
                await self._jira.get_issue(
                    query.issue_key, correlation_id=correlation_id
                ),
            )
            item = issues[0]
            if query.kind is TaskQueryKind.ISSUE_DUE_DATE:
                answer = (
                    f"{item.key} has no due date."
                    if item.due_date is None
                    else f"{item.key} is due on {item.due_date.isoformat()}."
                )
            elif query.kind is TaskQueryKind.ISSUE_STATUS:
                answer = f"{item.key}, {item.summary}, is currently {item.status}."
            else:
                assignee = item.assignee.display_name if item.assignee else "Unassigned"
                answer = (
                    f"{assignee} is assigned to {item.key}, {item.summary}, "
                    f"which is currently {item.status}."
                )
        elif query.kind is TaskQueryKind.EMPLOYEE_DUE_BY:
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
        else:
            assert query.jql is not None
            issues = await self._jira.search_issues(
                query.jql,
                project_key=query.project_key,
                correlation_id=correlation_id,
            )
            if query.kind is TaskQueryKind.BLOCKED_TASKS:
                issues = tuple(
                    item
                    for item in issues
                    if _blocker(item)
                    or any(
                        link.relationship.casefold() == "is blocked by"
                        for link in item.links
                    )
                )
            facts_for_answer = [_fact(item) for item in issues]
            if query.kind is TaskQueryKind.DONE_TASKS:
                answer = _format_list(
                    facts_for_answer,
                    empty="No tasks are currently Done.",
                    include_assignee=True,
                )
            elif query.kind is TaskQueryKind.MISSING_ESTIMATES:
                answer = _format_list(
                    facts_for_answer,
                    empty="No active tasks are missing a remaining estimate.",
                )
            elif query.kind is TaskQueryKind.BLOCKED_TASKS:
                answer = _format_list(
                    facts_for_answer, empty="No tasks are currently blocked."
                )
            elif query.kind is TaskQueryKind.OVERDUE_TASKS:
                answer = _format_list(
                    facts_for_answer, empty="No active tasks are overdue."
                )
            else:
                answer = _format_list(
                    facts_for_answer,
                    empty="No active tasks are due within seven days.",
                )
        facts = tuple(_fact(item) for item in issues)
        citation_fields = (
            ("duedate",)
            if query.kind is TaskQueryKind.ISSUE_DUE_DATE
            else ("summary", "status", "assignee")
        )
        citations = tuple(
            f"jira:{item.key}:{field}" for item in issues for field in citation_fields
        )
        return TaskQueryResult(
            answer=answer,
            tasks=facts,
            evidence_references=citations,
            correlation_id=correlation_id,
            context=GroundedAnswerContext(
                intent=query.kind.value,
                previous_question=question,
                issues=facts,
            ),
        )


def parse_task_query(
    question: str,
    references: EntityReferences,
    *,
    today: date,
    previous_context: GroundedAnswerContext | None = None,
) -> TaskQuery:
    folded = question.casefold()
    if "that task" in folded or "that issue" in folded:
        prior = previous_context.issues if previous_context else ()
        if not prior:
            raise ValueError("previous task context is required")
        if len(prior) > 1:
            return TaskQuery(
                kind=TaskQueryKind.AMBIGUOUS_REFERENT,
                project_key=references.project_key,
            )
        return TaskQuery(
            kind=TaskQueryKind.REFERENCED_TASK_ASSIGNEE,
            project_key=references.project_key,
            issue_key=prior[0].key,
        )
    issue_match = re.search(r"\b([A-Z][A-Z0-9]{1,19}-\d+)\b", question.upper())
    if issue_match:
        issue_key = issue_match.group(1)
        if not issue_key.startswith(f"{references.project_key}-"):
            raise ValueError("issue is outside the authorized project")
        kind = (
            TaskQueryKind.ISSUE_DUE_DATE
            if "due" in folded or "deadline" in folded
            else TaskQueryKind.ISSUE_ASSIGNEE
            if "who" in folded or "assign" in folded or "employee" in folded
            else TaskQueryKind.ISSUE_STATUS
        )
        return TaskQuery(
            kind=kind,
            project_key=references.project_key,
            issue_key=issue_key,
        )

    list_queries = (
        ("done", TaskQueryKind.DONE_TASKS, "statusCategory = Done"),
        (
            "missing estimate",
            TaskQueryKind.MISSING_ESTIMATES,
            "statusCategory != Done AND remainingEstimate is EMPTY",
        ),
        (
            "blocked",
            TaskQueryKind.BLOCKED_TASKS,
            "statusCategory != Done",
        ),
        (
            "overdue",
            TaskQueryKind.OVERDUE_TASKS,
            "statusCategory != Done AND duedate < startOfDay()",
        ),
        (
            "due soon",
            TaskQueryKind.DUE_SOON_TASKS,
            "statusCategory != Done AND duedate >= startOfDay() AND duedate <= 7d",
        ),
    )
    for phrase, kind, predicate in list_queries:
        if phrase in folded:
            jql = (
                f'project = "{references.project_key}" AND {predicate} ORDER BY key ASC'
            )
            return TaskQuery(
                kind=kind,
                project_key=references.project_key,
                jql=jql,
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


def _blocker(item: JiraIssueEvidence) -> str | None:
    return next(
        (
            str(field.value)
            for field in item.custom_fields
            if field.logical_name == "blocker_category" and field.value
        ),
        None,
    )


def _fact(item: JiraIssueEvidence) -> TaskFact:
    return TaskFact(
        key=item.key,
        summary=item.summary,
        status=item.status,
        assignee=item.assignee.display_name if item.assignee else None,
        due_date=item.due_date,
        remaining_hours=(
            item.remaining_estimate_seconds / 3600
            if item.remaining_estimate_seconds is not None
            else None
        ),
        blocker=_blocker(item),
        dependencies=tuple(
            f"{link.relationship}: {link.issue_key}" for link in item.links
        ),
    )


def _format_list(
    facts: list[TaskFact], *, empty: str, include_assignee: bool = False
) -> str:
    if not facts:
        return empty
    lines = []
    for fact in facts:
        line = f"{fact.key} — {fact.summary} — {fact.status}"
        if include_assignee:
            line += f" — assigned to {fact.assignee or 'Unassigned'}"
        lines.append(line + ".")
    return "\n".join(lines)
