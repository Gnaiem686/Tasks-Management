from datetime import UTC, date, datetime

import pytest
from agent_api.dashboard.models import (
    DashboardSnapshot,
    EmployeeSummary,
    ProjectSummary,
    TaskSummary,
    WorkloadDistribution,
)
from agent_api.evidence.focus import answer_context_from_evidence, build_answer_evidence
from agent_api.evidence.models import (
    EvidenceCategory,
    EvidenceEntity,
    EvidencePlan,
    EvidenceScope,
)
from agent_api.task_queries import GroundedAnswerContext, TaskFact


def wfd_snapshot() -> DashboardSnapshot:
    tasks = (
        _task(
            "WFD-4",
            "Migration",
            "Idea",
            "High",
            "EMP-002",
            date(2026, 8, 23),
            9,
            ("is blocked by: WFD-2",),
        ),
        _task(
            "WFD-5",
            "Security review",
            "Testing",
            "High",
            "EMP-002",
            date(2026, 8, 24),
            6,
            ("is blocked by: WFD-3",),
        ),
        _task(
            "WFD-9",
            "Dashboard",
            "In Progress",
            "Medium",
            "EMP-003",
            date(2026, 8, 24),
            10,
            ("blocks: WFD-11",),
        ),
        _task(
            "WFD-11",
            "Release",
            "Testing",
            "High",
            "EMP-003",
            date(2026, 8, 23),
            3,
            ("is blocked by: WFD-9",),
        ),
        _task(
            "WFD-12",
            "CI pipeline",
            "In Progress",
            "High",
            "EMP-004",
            date(2026, 8, 24),
            6,
            ("blocks: WFD-13",),
        ),
        _task(
            "WFD-13",
            "Deploy",
            "Idea",
            "Medium",
            "EMP-004",
            date(2026, 8, 27),
            8,
            ("is blocked by: WFD-12",),
        ),
        _task(
            "WFD-14",
            "Release plan",
            "Idea",
            "Medium",
            "EMP-004",
            date(2026, 8, 26),
            None,
            (),
        ),
    )
    return DashboardSnapshot(
        correlation_id="corr-focus",
        evidence_timestamp=datetime(2026, 8, 20, tzinfo=UTC),
        project=ProjectSummary(
            key="WFD",
            name="Workforce Real Data",
            total_tasks=len(tasks),
            completed_tasks=0,
            active_tasks=len(tasks),
            overdue_tasks=0,
            due_soon_tasks=5,
            blocked_tasks=4,
            missing_estimate_tasks=1,
            completion_percent=0,
        ),
        employees=(
            EmployeeSummary(
                employee_id="EMP-002",
                display_name="Mohammad Gnaiem",
                role="Backend Engineer",
                skills=("java", "spring"),
                capacity_hours=24,
                remaining_hours=36,
                active_tasks=5,
                score=64,
                level="high",
                top_risk="36h remaining exceeds 24h capacity.",
            ),
            EmployeeSummary(
                employee_id="EMP-003",
                display_name="emmpone1",
                role="Frontend Engineer",
                skills=("javascript",),
                capacity_hours=24,
                remaining_hours=18,
                active_tasks=3,
                score=38,
                level="medium",
                top_risk="WFD-11 is blocked by WFD-9.",
            ),
            EmployeeSummary(
                employee_id="EMP-004",
                display_name="gnaiem",
                role="DevOps Engineer",
                skills=("kubernetes",),
                capacity_hours=24,
                remaining_hours=None,
                active_tasks=4,
                score=None,
                level="insufficient-data",
                top_risk="WFD-14 is missing a remaining estimate.",
            ),
        ),
        tasks=tasks,
        alerts=(),
        workload=WorkloadDistribution(overloaded=1, balanced=1, insufficient_data=1),
    )


def _task(
    key: str,
    summary: str,
    status: str,
    priority: str,
    employee_id: str,
    due_date: date | None,
    remaining_hours: float | None,
    dependencies: tuple[str, ...],
) -> TaskSummary:
    return TaskSummary(
        key=key,
        summary=summary,
        status=status,
        priority=priority,
        assignee_id=employee_id,
        assignee_name=employee_id,
        due_date=due_date,
        original_hours=remaining_hours,
        remaining_hours=remaining_hours,
        required_skills=(),
        blocker=None,
        dependencies=dependencies,
        jira_url=f"https://example.atlassian.net/browse/{key}",
    )


def blocked_task_plan() -> EvidencePlan:
    return EvidencePlan(
        scope=EvidenceScope.TASK,
        evidence_categories=(
            EvidenceCategory.JIRA_ISSUES,
            EvidenceCategory.DEPENDENCIES_AND_BLOCKERS,
        ),
        exhaustive=True,
    )


def deadline_task_plan() -> EvidencePlan:
    return EvidencePlan(
        scope=EvidenceScope.TASK,
        evidence_categories=(
            EvidenceCategory.JIRA_ISSUES,
            EvidenceCategory.DEADLINES,
            EvidenceCategory.DEPENDENCIES_AND_BLOCKERS,
        ),
        exhaustive=True,
    )


def test_blocked_question_focuses_every_actually_blocked_task() -> None:
    focused = build_answer_evidence(
        question="Which work is blocked right now?",
        snapshot=wfd_snapshot(),
        plan=blocked_task_plan(),
        previous_context=None,
    )

    assert [task.key for task in focused.tasks] == [
        "WFD-4",
        "WFD-5",
        "WFD-11",
        "WFD-13",
    ]
    assert focused.required_task_keys == (
        "WFD-4",
        "WFD-5",
        "WFD-11",
        "WFD-13",
    )
    assert focused.exhaustive is True


def test_deadline_focus_has_concrete_ranked_tasks() -> None:
    focused = build_answer_evidence(
        question="Which tasks are most likely to miss their deadlines?",
        snapshot=wfd_snapshot(),
        plan=deadline_task_plan(),
        previous_context=None,
    )

    assert focused.tasks
    assert len(focused.tasks) == 5
    assert all(task.due_date is not None for task in focused.tasks)
    assert any(task.blocked for task in focused.tasks)
    assert focused.tasks[0].key == "WFD-4"
    assert focused.required_task_keys == tuple(task.key for task in focused.tasks)


def test_overdue_focus_keeps_deadline_context_but_requires_only_overdue_tasks() -> None:
    snapshot = wfd_snapshot()
    snapshot = snapshot.model_copy(
        update={"evidence_timestamp": datetime(2026, 8, 25, tzinfo=UTC)}
    )

    focused = build_answer_evidence(
        question="Which tasks are overdue?",
        snapshot=snapshot,
        plan=deadline_task_plan(),
        previous_context=None,
    )

    assert len(focused.tasks) == 7
    assert focused.required_task_keys == (
        "WFD-4",
        "WFD-11",
        "WFD-5",
        "WFD-12",
        "WFD-9",
    )
    context = answer_context_from_evidence(focused)
    assert tuple(task.key for task in context.issues) == focused.required_task_keys


def test_plural_follow_up_reuses_every_previous_task() -> None:
    previous = GroundedAnswerContext(
        intent="deadline_risk",
        issues=(
            TaskFact(key="WFD-11", summary="Release", status="Testing"),
            TaskFact(key="WFD-13", summary="Deploy", status="Idea"),
        ),
    )
    plan = EvidencePlan(
        scope=EvidenceScope.TASK,
        entities=(
            EvidenceEntity(kind="task", identifier="WFD-11"),
            EvidenceEntity(kind="task", identifier="WFD-13"),
        ),
        evidence_categories=(EvidenceCategory.JIRA_ISSUES,),
        exhaustive=True,
    )

    focused = build_answer_evidence(
        question="Name those tasks",
        snapshot=wfd_snapshot(),
        plan=plan,
        previous_context=previous,
    )

    assert [task.key for task in focused.tasks] == ["WFD-11", "WFD-13"]
    assert focused.required_task_keys == ("WFD-11", "WFD-13")


def test_all_task_question_requires_every_selected_task() -> None:
    focused = build_answer_evidence(
        question="List all tasks in this project",
        snapshot=wfd_snapshot(),
        plan=EvidencePlan(
            scope=EvidenceScope.TASK,
            evidence_categories=(EvidenceCategory.JIRA_ISSUES,),
            exhaustive=True,
        ),
        previous_context=None,
    )

    assert focused.required_task_keys == tuple(task.key for task in focused.tasks)


def test_employee_task_question_requires_only_that_employees_tasks() -> None:
    snapshot = wfd_snapshot()
    snapshot = snapshot.model_copy(
        update={
            "employees": snapshot.employees
            + (
                EmployeeSummary(
                    employee_id="EMP-001",
                    display_name="Mohammad",
                    role="Full Stack Engineer",
                    skills=("python",),
                    capacity_hours=28,
                    remaining_hours=12,
                    active_tasks=1,
                    score=17,
                    level="low",
                    top_risk="Within capacity.",
                ),
            ),
            "tasks": snapshot.tasks
            + (
                _task(
                    "WFD-1",
                    "Other employee task",
                    "In Progress",
                    "High",
                    "EMP-001",
                    date(2026, 8, 21),
                    3,
                    (),
                ),
            ),
        }
    )

    focused = build_answer_evidence(
        question="What are the tasks belonging to Mohammad Gnaiem?",
        snapshot=snapshot,
        plan=EvidencePlan(
            scope=EvidenceScope.MIXED,
            evidence_categories=(
                EvidenceCategory.JIRA_ISSUES,
                EvidenceCategory.WORKFORCE_PROFILES,
            ),
            exhaustive=True,
        ),
        previous_context=None,
    )

    assert [employee.display_name for employee in focused.employees] == [
        "Mohammad Gnaiem"
    ]
    assert focused.required_task_keys == ("WFD-4", "WFD-5")
    assert tuple(task.key for task in focused.tasks) == focused.required_task_keys


def test_employee_risk_focus_distinguishes_missing_estimate_from_overload() -> None:
    focused = build_answer_evidence(
        question="Which employees are at risk and why?",
        snapshot=wfd_snapshot(),
        plan=EvidencePlan(
            scope=EvidenceScope.EMPLOYEE,
            evidence_categories=(
                EvidenceCategory.WORKFORCE_PROFILES,
                EvidenceCategory.CAPACITY_AND_WORKLOAD,
                EvidenceCategory.RISK_RESULTS,
            ),
            exhaustive=True,
        ),
        previous_context=None,
    )

    assert [employee.employee_id for employee in focused.employees] == [
        "EMP-002",
        "EMP-003",
        "EMP-004",
    ]
    missing = focused.employees[-1]
    assert missing.risk_level == "insufficient-data"
    assert missing.remaining_hours is None


@pytest.mark.parametrize("model_entity", ("unknown-model-label", "EMP-002"))
def test_exhaustive_employee_question_ignores_model_entity_filter(
    model_entity: str,
) -> None:
    focused = build_answer_evidence(
        question="Which employees are at risk and why?",
        snapshot=wfd_snapshot(),
        plan=EvidencePlan(
            scope=EvidenceScope.EMPLOYEE,
            entities=(EvidenceEntity(kind="employee", identifier=model_entity),),
            evidence_categories=(
                EvidenceCategory.WORKFORCE_PROFILES,
                EvidenceCategory.CAPACITY_AND_WORKLOAD,
                EvidenceCategory.RISK_RESULTS,
            ),
            exhaustive=True,
        ),
        previous_context=None,
    )

    assert [employee.employee_id for employee in focused.employees] == [
        "EMP-002",
        "EMP-003",
        "EMP-004",
    ]
    assert {task.key for task in focused.tasks} >= {"WFD-9", "WFD-11"}
