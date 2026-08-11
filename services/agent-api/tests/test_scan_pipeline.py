from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from agent_api.dependencies import EvidenceBundle
from agent_api.scans.pipeline import EmployeeOverloadScanPipeline
from workforce_risk.models import EmployeeOverloadInput, RiskResult


class EvidenceProvider:
    async def get_employee_overload(
        self, employee_id: str, project_key: str, correlation_id: str
    ) -> EvidenceBundle:
        return EvidenceBundle(
            input=EmployeeOverloadInput(
                employee_id=employee_id,
                environment="test",
                remaining_estimated_hours=70,
                available_capacity_hours=40,
                overdue_tasks=4,
                blocked_or_blocking_tasks=3,
                urgent_high_priority_tasks=3,
                due_soon_tasks=3,
                active_tasks=8,
                concurrent_projects=3,
                stale_tasks=3,
                evidence_timestamp=datetime.now(UTC),
            )
        )


class ScoringClient:
    async def score(
        self, input_data: EmployeeOverloadInput, correlation_id: str
    ) -> dict[str, Any]:
        return {
            "subject_id": input_data.employee_id,
            "environment": "test",
            "score": 88,
            "level": "critical",
            "confidence": "high",
            "scored_at": datetime.now(UTC).isoformat(),
            "evidence_timestamp": input_data.evidence_timestamp.isoformat(),
            "scoring_model_version": "employee-overload-v1",
            "factors": [],
            "thresholds": {"low": 0, "medium": 30, "high": 60, "critical": 80},
            "evidence_references": [],
            "missing_evidence": [],
            "excluded_evidence": [],
        }


class Sink:
    def __init__(self) -> None:
        self.calls: list[tuple[EmployeeOverloadInput, RiskResult, str, str]] = []

    async def persist(
        self,
        *,
        input_data: EmployeeOverloadInput,
        result: RiskResult,
        scope: str,
        correlation_id: str,
    ) -> tuple[str, str]:
        self.calls.append((input_data, result, scope, correlation_id))
        return "risk-1", "alert-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scan_pipeline_scores_and_persists_configured_employees() -> None:
    sink = Sink()
    pipeline = EmployeeOverloadScanPipeline(
        evidence=EvidenceProvider(),
        scoring=ScoringClient(),
        sink=sink,
        employee_ids=("EMP-002",),
    )

    result = await pipeline.run(scope="WRD", correlation_id="corr-demo")

    assert result.degraded is False
    assert result.risk_result_ids == ("risk-1",)
    assert result.alert_ids == ("alert-1",)
    assert result.report_id is None
    assert sink.calls[0][2:] == ("WRD", "corr-demo")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scan_pipeline_marks_partial_evidence_degraded() -> None:
    class DegradedEvidence(EvidenceProvider):
        async def get_employee_overload(
            self, employee_id: str, project_key: str, correlation_id: str
        ) -> EvidenceBundle:
            bundle = await super().get_employee_overload(
                employee_id, project_key, correlation_id
            )
            return bundle.model_copy(
                update={"degraded": True, "missing_sources": ("jira_activity",)}
            )

    pipeline = EmployeeOverloadScanPipeline(
        evidence=DegradedEvidence(),
        scoring=ScoringClient(),
        sink=Sink(),
        employee_ids=("EMP-002",),
    )

    result = await pipeline.run(scope="WRD", correlation_id="corr-degraded")

    assert result.degraded is True
