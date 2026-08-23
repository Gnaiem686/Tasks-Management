from __future__ import annotations

from datetime import UTC, datetime

from agent_api.dashboard.models import (
    DashboardSnapshot,
    EmployeeSummary,
    ProjectSummary,
    TaskSummary,
    WorkloadDistribution,
)
from agent_api.evidence.derivation import rank_reassignment_candidates


def test_candidate_ranking_uses_headroom_and_required_skills() -> None:
    employees = (
        EmployeeSummary(
            employee_id="EMP-1",
            display_name="Overloaded",
            role="dev",
            skills=("java", "spring"),
            capacity_hours=24,
            remaining_hours=36,
            active_tasks=2,
            score=80,
            level="high",
            top_risk="capacity",
        ),
        EmployeeSummary(
            employee_id="EMP-2",
            display_name="Best",
            role="dev",
            skills=("java", "spring"),
            capacity_hours=40,
            remaining_hours=10,
            active_tasks=1,
            score=10,
            level="low",
            top_risk="none",
        ),
        EmployeeSummary(
            employee_id="EMP-3",
            display_name="No skill",
            role="dev",
            skills=("python",),
            capacity_hours=40,
            remaining_hours=0,
            active_tasks=0,
            score=5,
            level="low",
            top_risk="none",
        ),
    )
    snapshot = DashboardSnapshot(
        correlation_id="corr-1",
        evidence_timestamp=datetime.now(UTC),
        project=ProjectSummary(
            key="WFD",
            name="Demo",
            total_tasks=1,
            completed_tasks=0,
            active_tasks=1,
            overdue_tasks=0,
            due_soon_tasks=0,
            blocked_tasks=0,
            missing_estimate_tasks=0,
            completion_percent=0,
        ),
        employees=employees,
        tasks=(
            TaskSummary(
                key="WFD-1",
                summary="Java work",
                status="In Progress",
                priority="High",
                assignee_id="EMP-1",
                assignee_name="Overloaded",
                due_date=None,
                original_hours=10,
                remaining_hours=8,
                required_skills=("java", "spring"),
                blocker=None,
                dependencies=(),
                jira_url="https://example/WFD-1",
            ),
        ),
        alerts=(),
        workload=WorkloadDistribution(overloaded=1, balanced=2, insufficient_data=0),
    )

    ranked = rank_reassignment_candidates(snapshot, source_employee_id="EMP-1")

    assert ranked.status == "success"
    assert ranked.candidates[0].employee_id == "EMP-2"
    assert ranked.candidates[0].eligible is True
    assert ranked.candidates[1].employee_id == "EMP-3"
    assert ranked.candidates[1].eligible is False


def test_candidate_ranking_returns_insufficient_data_without_throwing() -> None:
    snapshot = DashboardSnapshot(
        correlation_id="corr-missing",
        evidence_timestamp=datetime.now(UTC),
        project=ProjectSummary(
            key="WFD",
            name="Demo",
            total_tasks=0,
            completed_tasks=0,
            active_tasks=0,
            overdue_tasks=0,
            due_soon_tasks=0,
            blocked_tasks=0,
            missing_estimate_tasks=0,
            completion_percent=0,
        ),
        employees=(
            EmployeeSummary(
                employee_id="EMP-1",
                display_name="Source",
                role="dev",
                skills=(),
                capacity_hours=24,
                remaining_hours=30,
                active_tasks=1,
                score=80,
                level="high",
                top_risk="capacity",
            ),
            EmployeeSummary(
                employee_id="EMP-2",
                display_name="Unknown",
                role="dev",
                skills=(),
                capacity_hours=None,
                remaining_hours=0,
                active_tasks=0,
                score=None,
                level="insufficient-data",
                top_risk="missing capacity",
            ),
        ),
        tasks=(),
        alerts=(),
        workload=WorkloadDistribution(overloaded=1, balanced=0, insufficient_data=1),
    )

    result = rank_reassignment_candidates(snapshot, source_employee_id="EMP-1")

    assert result.status == "insufficient_data"
    assert result.candidates == ()
    assert result.missing_data
