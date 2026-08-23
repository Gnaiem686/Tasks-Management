from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agent_api.dashboard.models import (
    DashboardSnapshot,
    EmployeeSummary,
    ProjectSummary,
    WorkloadDistribution,
)
from agent_api.evidence.collectors import UniversalEvidenceCollector
from agent_api.evidence.models import EvidenceCategory, EvidencePlan, EvidenceScope


class ProjectTool:
    async def build(self, project_key: str, correlation_id: str) -> DashboardSnapshot:
        return DashboardSnapshot(
            correlation_id=correlation_id,
            evidence_timestamp=datetime.now(UTC),
            project=ProjectSummary(
                key=project_key,
                name="Demo",
                total_tasks=2,
                completed_tasks=0,
                active_tasks=2,
                overdue_tasks=0,
                due_soon_tasks=1,
                blocked_tasks=0,
                missing_estimate_tasks=0,
                completion_percent=0,
            ),
            employees=(
                EmployeeSummary(
                    employee_id="EMP-1",
                    display_name="A",
                    role="Developer",
                    skills=("java",),
                    capacity_hours=24,
                    remaining_hours=36,
                    active_tasks=2,
                    score=80,
                    level="high",
                    top_risk="overloaded",
                ),
            ),
            tasks=(),
            alerts=(),
            workload=WorkloadDistribution(
                overloaded=1, balanced=0, insufficient_data=0
            ),
        )


class HistoryTool:
    async def load(
        self, project_key: str, correlation_id: str
    ) -> tuple[dict[str, object], ...]:
        assert project_key == "WFD"
        assert correlation_id == "corr-2"
        return (
            {
                "record_type": "progress_event",
                "issue_key": "WFD-1",
                "event_type": "remaining_estimate_changed",
                "old_value": 10.0,
                "new_value": 6.0,
                "occurred_at": "2026-08-22T08:00:00+00:00",
            },
        )


@pytest.mark.asyncio
async def test_collector_uses_exact_capacity_semantics() -> None:
    bundle = await UniversalEvidenceCollector(ProjectTool()).collect(
        EvidencePlan(
            scope=EvidenceScope.PROJECT,
            evidence_categories=(EvidenceCategory.CAPACITY_AND_WORKLOAD,),
        ),
        project_key="WFD",
        correlation_id="corr-1",
    )

    capacity = bundle.capacity_and_workload[0]
    assert capacity.available_capacity_hours == 0
    assert capacity.capacity_headroom_hours == -12
    assert capacity.utilization_percent == 150
    assert bundle.answer_evidence is not None
    assert bundle.answer_evidence.question_focus == ""


@pytest.mark.asyncio
async def test_missing_optional_history_is_bundle_data() -> None:
    bundle = await UniversalEvidenceCollector(ProjectTool()).collect(
        EvidencePlan(
            scope=EvidenceScope.PROJECT, evidence_categories=(EvidenceCategory.HISTORY,)
        ),
        project_key="WFD",
        correlation_id="corr-2",
    )

    assert bundle.missing_data[0].category is EvidenceCategory.HISTORY


@pytest.mark.asyncio
async def test_requested_history_is_loaded_into_bundle() -> None:
    bundle = await UniversalEvidenceCollector(
        ProjectTool(), history_reader=HistoryTool()
    ).collect(
        EvidencePlan(
            scope=EvidenceScope.PROJECT,
            evidence_categories=(EvidenceCategory.HISTORY,),
        ),
        project_key="WFD",
        correlation_id="corr-2",
        question="Has work progressed this week?",
    )

    assert bundle.history[0]["issue_key"] == "WFD-1"
    assert not any(
        item.category is EvidenceCategory.HISTORY for item in bundle.missing_data
    )
