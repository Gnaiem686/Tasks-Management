from __future__ import annotations

import re
from datetime import timedelta

from agent_api.dashboard.models import DashboardSnapshot, EmployeeSummary, TaskSummary
from agent_api.evidence.models import (
    AnswerEmployeeEvidence,
    AnswerEvidenceSet,
    AnswerTaskEvidence,
    EvidenceCategory,
    EvidencePlan,
    MissingData,
)
from agent_api.task_queries import GroundedAnswerContext, TaskFact

_DONE_STATUSES = frozenset({"done", "closed", "resolved", "complete", "completed"})
_PRIORITY_RANK = {
    "highest": 0,
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "lowest": 4,
}


def build_answer_evidence(
    *,
    question: str,
    snapshot: DashboardSnapshot,
    plan: EvidencePlan,
    previous_context: GroundedAnswerContext | None,
) -> AnswerEvidenceSet:
    """Derive the bounded facts Bedrock must use for this particular answer."""

    folded = question.casefold()
    task_by_key = {task.key: task for task in snapshot.tasks}
    explicit_keys = [
        entity.identifier for entity in plan.entities if entity.kind == "task"
    ]
    if not explicit_keys and previous_context is not None and _refers_to_prior(folded):
        explicit_keys = [issue.key for issue in previous_context.issues]

    selected_tasks: list[TaskSummary]
    required_tasks: list[TaskSummary]
    if explicit_keys:
        selected_tasks = [
            task_by_key[key] for key in explicit_keys if key in task_by_key
        ]
        required_tasks = list(selected_tasks)
    elif _asks_blocked(folded):
        selected_tasks = [task for task in snapshot.tasks if _is_blocked(task)]
        required_tasks = list(selected_tasks)
    elif "missing" in folded and "estimate" in folded:
        selected_tasks = [
            task
            for task in snapshot.tasks
            if not _is_done(task) and task.remaining_hours is None
        ]
        required_tasks = list(selected_tasks)
    elif any(word in folded for word in ("deadline", "due", "overdue")):
        selected_tasks = sorted(
            (
                task
                for task in snapshot.tasks
                if not _is_done(task) and task.due_date is not None
            ),
            key=lambda task: _deadline_rank(task, snapshot),
        )
        if any(
            phrase in folded
            for phrase in ("most likely", "highest risk", "riskiest", "top ")
        ):
            selected_tasks = selected_tasks[:5]
            required_tasks = list(selected_tasks)
        elif "overdue" in folded:
            today = snapshot.evidence_timestamp.date()
            required_tasks = [
                task
                for task in selected_tasks
                if task.due_date is not None and task.due_date < today
            ]
        elif "due soon" in folded:
            today = snapshot.evidence_timestamp.date()
            required_tasks = [
                task
                for task in selected_tasks
                if task.due_date is not None
                and today <= task.due_date <= today + timedelta(days=7)
            ]
        else:
            required_tasks = list(selected_tasks)
    elif plan.scope.value == "task":
        selected_tasks = list(snapshot.tasks)
        required_tasks = list(selected_tasks)
    else:
        selected_tasks = []
        required_tasks = []

    explicit_employee_ids = [
        entity.identifier for entity in plan.entities if entity.kind == "employee"
    ]
    if plan.exhaustive and any(
        phrase in folded
        for phrase in (
            "which employees",
            "all employees",
            "employees are",
            "which people",
            "who is at risk",
        )
    ):
        # The manager asked for a project-wide employee set. A model-planned
        # entity hint must not silently narrow that authoritative scope.
        explicit_employee_ids = []
    selected_employees = _select_employees(
        snapshot,
        folded=folded,
        explicit_ids=explicit_employee_ids,
        include_all=plan.scope.value in {"employee", "mixed"},
    )
    if selected_employees and not selected_tasks:
        employee_ids = {employee.employee_id for employee in selected_employees}
        selected_tasks = [
            task for task in snapshot.tasks if task.assignee_id in employee_ids
        ]
        required_tasks = list(selected_tasks)
    elif selected_employees and plan.scope.value == "task" and not explicit_keys:
        employee_ids = {employee.employee_id for employee in selected_employees}
        selected_tasks = [
            task for task in selected_tasks if task.assignee_id in employee_ids
        ]
        required_keys = {task.key for task in required_tasks}
        required_tasks = [task for task in selected_tasks if task.key in required_keys]
    if selected_tasks and not selected_employees:
        assignee_ids = {task.assignee_id for task in selected_tasks if task.assignee_id}
        selected_employees = [
            employee
            for employee in snapshot.employees
            if employee.employee_id in assignee_ids
        ]

    missing_data = _focused_missing_data(
        snapshot=snapshot,
        tasks=selected_tasks,
        employees=selected_employees,
        requested=set(plan.evidence_categories),
    )
    return AnswerEvidenceSet(
        question_focus=question,
        tasks=tuple(_task_evidence(task, snapshot) for task in selected_tasks),
        required_task_keys=tuple(task.key for task in required_tasks),
        employees=tuple(
            _employee_evidence(employee, snapshot) for employee in selected_employees
        ),
        exhaustive=plan.exhaustive,
        missing_data=missing_data,
    )


def answer_context_from_evidence(evidence: AnswerEvidenceSet) -> GroundedAnswerContext:
    required = {key.upper() for key in evidence.required_task_keys}
    context_tasks = (
        tuple(task for task in evidence.tasks if task.key.upper() in required)
        if required
        else evidence.tasks
    )
    return GroundedAnswerContext(
        intent="focused_project_evidence",
        previous_question=evidence.question_focus,
        issues=tuple(
            TaskFact(
                key=task.key,
                summary=task.summary,
                status=task.status,
                assignee=task.assignee,
                due_date=task.due_date,
                remaining_hours=task.remaining_hours,
                blocker=task.blocker,
                dependencies=task.dependencies,
            )
            for task in context_tasks
        ),
        employee_ids=tuple(employee.employee_id for employee in evidence.employees),
        exhaustive=evidence.exhaustive,
    )


def _select_employees(
    snapshot: DashboardSnapshot,
    *,
    folded: str,
    explicit_ids: list[str],
    include_all: bool,
) -> list[EmployeeSummary]:
    if explicit_ids:
        wanted = {identifier.casefold() for identifier in explicit_ids}
        matched = [
            item
            for item in snapshot.employees
            if item.employee_id.casefold() in wanted
            or item.display_name.casefold() in wanted
        ]
        if matched or not include_all:
            return matched
        # A model-selected label must not silently empty an exhaustive employee
        # question. The authoritative snapshot remains the project-wide scope.
        return list(snapshot.employees)
    named = _named_employees(snapshot.employees, folded)
    return list(snapshot.employees) if include_all and not named else named


def _named_employees(
    employees: tuple[EmployeeSummary, ...], folded: str
) -> list[EmployeeSummary]:
    directly_named = {
        employee.employee_id
        for employee in employees
        if re.search(
            rf"(?<!\w){re.escape(employee.employee_id.casefold())}(?!\w)",
            folded,
        )
    }
    matches: list[tuple[int, int, EmployeeSummary]] = []
    for employee in employees:
        pattern = re.compile(
            rf"(?<!\w){re.escape(employee.display_name.casefold())}(?!\w)"
        )
        matches.extend(
            (match.start(), match.end(), employee) for match in pattern.finditer(folded)
        )
    accepted_spans: list[tuple[int, int]] = []
    for start, end, employee in sorted(
        matches,
        key=lambda item: (-(item[1] - item[0]), item[0]),
    ):
        if any(
            start < accepted_end and end > accepted_start
            for accepted_start, accepted_end in accepted_spans
        ):
            continue
        accepted_spans.append((start, end))
        directly_named.add(employee.employee_id)
    return [
        employee for employee in employees if employee.employee_id in directly_named
    ]


def _task_evidence(
    task: TaskSummary, snapshot: DashboardSnapshot
) -> AnswerTaskEvidence:
    today = snapshot.evidence_timestamp.date()
    missing = []
    if task.priority is None:
        missing.append("priority")
    if task.due_date is None:
        missing.append("due_date")
    if task.remaining_hours is None:
        missing.append("remaining_hours")
    return AnswerTaskEvidence(
        key=task.key,
        summary=task.summary,
        status=task.status,
        priority=task.priority or "Unknown",
        assignee=task.assignee_name,
        due_date=task.due_date,
        remaining_hours=task.remaining_hours,
        blocker=task.blocker,
        dependencies=task.dependencies,
        blocked=_is_blocked(task),
        blocks_downstream=tuple(
            dependency.split(":", 1)[1].strip()
            for dependency in task.dependencies
            if dependency.casefold().startswith("blocks:")
        ),
        overdue=(
            not _is_done(task) and task.due_date is not None and task.due_date < today
        ),
        due_soon=(
            not _is_done(task)
            and task.due_date is not None
            and today <= task.due_date <= today + timedelta(days=7)
        ),
        missing_fields=tuple(missing),
    )


def _employee_evidence(
    employee: EmployeeSummary, snapshot: DashboardSnapshot
) -> AnswerEmployeeEvidence:
    task_keys = tuple(
        task.key for task in snapshot.tasks if task.assignee_id == employee.employee_id
    )
    available = (
        max(employee.capacity_hours - employee.remaining_hours, 0.0)
        if employee.capacity_hours is not None and employee.remaining_hours is not None
        else None
    )
    return AnswerEmployeeEvidence(
        employee_id=employee.employee_id,
        display_name=employee.display_name,
        role=employee.role,
        skills=employee.skills,
        capacity_hours=employee.capacity_hours,
        remaining_hours=employee.remaining_hours,
        available_capacity_hours=available,
        active_tasks=employee.active_tasks,
        risk_level=employee.level,
        top_risk=employee.top_risk,
        task_keys=task_keys,
    )


def _focused_missing_data(
    *,
    snapshot: DashboardSnapshot,
    tasks: list[TaskSummary],
    employees: list[EmployeeSummary],
    requested: set[EvidenceCategory],
) -> tuple[MissingData, ...]:
    missing: list[MissingData] = []
    for task in tasks:
        if task.remaining_hours is None:
            missing.append(
                MissingData(
                    category=EvidenceCategory.JIRA_ISSUES,
                    reason="remaining estimate is unavailable",
                    entity=f"task:{task.key}",
                    required_for_claim=True,
                )
            )
    for employee in employees:
        if employee.capacity_hours is None or employee.capacity_hours <= 0:
            missing.append(
                MissingData(
                    category=EvidenceCategory.CAPACITY_AND_WORKLOAD,
                    reason="configured capacity is unavailable",
                    entity=f"employee:{employee.employee_id}",
                    required_for_claim=True,
                )
            )
        if EvidenceCategory.SKILLS_AND_SENIORITY in requested and not employee.skills:
            missing.append(
                MissingData(
                    category=EvidenceCategory.SKILLS_AND_SENIORITY,
                    reason="documented skills are unavailable",
                    entity=f"employee:{employee.employee_id}",
                    required_for_claim=True,
                )
            )
    return tuple(missing)


def _is_done(task: TaskSummary) -> bool:
    return task.status.casefold() in _DONE_STATUSES


def _is_blocked(task: TaskSummary) -> bool:
    return bool(task.blocker) or any(
        dependency.casefold().startswith("is blocked by:")
        for dependency in task.dependencies
    )


def _asks_blocked(folded: str) -> bool:
    return "blocked" in folded or "blocker" in folded


def _refers_to_prior(folded: str) -> bool:
    return any(
        phrase in folded
        for phrase in ("that task", "those tasks", "these tasks", "them")
    )


def _deadline_rank(
    task: TaskSummary, snapshot: DashboardSnapshot
) -> tuple[object, ...]:
    today = snapshot.evidence_timestamp.date()
    assert task.due_date is not None
    return (
        0 if task.due_date < today else 1,
        0 if _is_blocked(task) else 1,
        task.due_date,
        _PRIORITY_RANK.get((task.priority or "").casefold(), 5),
        -(task.remaining_hours or 0.0),
        task.key,
    )
