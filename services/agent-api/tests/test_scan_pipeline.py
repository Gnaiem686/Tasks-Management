from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from agent_api.dependencies import EvidenceBundle
from agent_api.risk_evidence import RiskEvidenceDossier
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
    def __init__(self) -> None:
        self.correlation_ids: list[str] = []

    async def score(
        self, input_data: EmployeeOverloadInput, correlation_id: str
    ) -> dict[str, Any]:
        self.correlation_ids.append(correlation_id)
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
        self.calls: list[
            tuple[
                EmployeeOverloadInput,
                RiskResult,
                RiskEvidenceDossier | None,
                str,
                str,
            ]
        ] = []

    async def persist(
        self,
        *,
        input_data: EmployeeOverloadInput,
        result: RiskResult,
        evidence_dossier: RiskEvidenceDossier | None,
        scope: str,
        correlation_id: str,
    ) -> tuple[str, str]:
        self.calls.append((input_data, result, evidence_dossier, scope, correlation_id))
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
    assert sink.calls[0][3:] == ("WRD", "corr-demo")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scan_persists_immutable_task_dossier_when_available() -> None:
    class DossierEvidence(EvidenceProvider):
        async def get_employee_overload(
            self, employee_id: str, project_key: str, correlation_id: str
        ) -> EvidenceBundle:
            bundle = await super().get_employee_overload(
                employee_id, project_key, correlation_id
            )
            return bundle.model_copy(
                update={
                    "evidence_dossier": RiskEvidenceDossier(
                        employee_id=employee_id,
                        project_key=project_key,
                        observed_at=datetime(2026, 8, 18, 10, tzinfo=UTC),
                        available_capacity_hours=40,
                        total_remaining_hours=72,
                        tasks=(),
                        overdue_task_keys=("WRD-4",),
                        due_soon_task_keys=("WRD-6",),
                        blocked_task_keys=("WRD-6",),
                        missing_evidence=(),
                        evidence_references=("jira:WRD-4:duedate",),
                    )
                }
            )

    sink = Sink()
    await EmployeeOverloadScanPipeline(
        evidence=DossierEvidence(),
        scoring=ScoringClient(),
        sink=sink,
        employee_ids=("EMP-003",),
    ).run(scope="WRD", correlation_id="corr-history")

    assert sink.calls[0][2] is not None
    assert sink.calls[0][2].total_remaining_hours == 72


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scan_pipeline_uses_unique_child_correlation_per_employee() -> None:
    scoring = ScoringClient()
    pipeline = EmployeeOverloadScanPipeline(
        evidence=EvidenceProvider(),
        scoring=scoring,
        sink=Sink(),
        employee_ids=("EMP-001", "EMP-002", "EMP-006"),
    )

    await pipeline.run(scope="WRD", correlation_id="corr-scan")

    assert scoring.correlation_ids == [
        "corr-scan:EMP-001",
        "corr-scan:EMP-002",
        "corr-scan:EMP-006",
    ]
