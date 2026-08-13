from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from workforce_persistence.alert_repository import AlertRepository
from workforce_persistence.database import Database
from workforce_persistence.models import EvidenceSnapshot, RiskResultRecord
from workforce_risk.models import EmployeeOverloadInput, RiskResult
from workforce_risk.scans.service import PipelineResult

from agent_api.dependencies import EmployeeEvidenceProvider, WorkforceScoringClient


class ScanResultSink(Protocol):
    async def persist(
        self,
        *,
        input_data: EmployeeOverloadInput,
        result: RiskResult,
        scope: str,
        correlation_id: str,
    ) -> tuple[str, str | None]: ...


class EmployeeOverloadScanPipeline:
    """Reuse the interactive evidence and scoring path for scheduled scans."""

    def __init__(
        self,
        *,
        evidence: EmployeeEvidenceProvider,
        scoring: WorkforceScoringClient,
        sink: ScanResultSink,
        employee_ids: tuple[str, ...],
    ) -> None:
        if not employee_ids:
            raise ValueError("at least one scan employee must be configured")
        self._evidence = evidence
        self._scoring = scoring
        self._sink = sink
        self._employee_ids = employee_ids

    async def run(self, *, scope: str, correlation_id: str) -> PipelineResult:
        risk_ids: list[str] = []
        alert_ids: list[str] = []
        degraded = False
        for employee_id in self._employee_ids:
            bundle = await self._evidence.get_employee_overload(
                employee_id, scope, correlation_id
            )
            degraded = degraded or bundle.degraded
            result = RiskResult.model_validate(
                await self._scoring.score(bundle.input, correlation_id)
            )
            risk_id, alert_id = await self._sink.persist(
                input_data=bundle.input,
                result=result,
                scope=scope,
                correlation_id=correlation_id,
            )
            risk_ids.append(risk_id)
            if alert_id is not None:
                alert_ids.append(alert_id)
        return PipelineResult(
            degraded=degraded,
            risk_result_ids=tuple(risk_ids),
            alert_ids=tuple(alert_ids),
            report_id=None,
        )


class DatabaseScanResultSink:
    def __init__(self, database: Database, *, environment: str) -> None:
        self._database = database
        self._environment = environment

    async def persist(
        self,
        *,
        input_data: EmployeeOverloadInput,
        result: RiskResult,
        scope: str,
        correlation_id: str,
    ) -> tuple[str, str | None]:
        if (
            input_data.environment != self._environment
            or result.environment != self._environment
        ):
            raise ValueError("scan result environment mismatch")
        now = datetime.now(UTC)
        material = input_data.model_dump_json(exclude={"evidence_timestamp"})
        fingerprint = hashlib.sha256(material.encode()).hexdigest()
        async with self._database.transaction() as session:
            snapshot = await session.scalar(
                select(EvidenceSnapshot).where(
                    EvidenceSnapshot.environment == self._environment,
                    EvidenceSnapshot.subject_type == "employee",
                    EvidenceSnapshot.subject_id == result.subject_id,
                    EvidenceSnapshot.fingerprint == fingerprint,
                )
            )
            if snapshot is None:
                snapshot = EvidenceSnapshot(
                    id=uuid.uuid4(),
                    environment=self._environment,
                    created_at=now,
                    subject_type="employee",
                    subject_id=result.subject_id,
                    fingerprint=fingerprint,
                    evidence=input_data.model_dump(mode="json"),
                    observed_at=input_data.evidence_timestamp,
                )
                session.add(snapshot)
                await session.flush()
            risk = RiskResultRecord(
                id=uuid.uuid4(),
                environment=self._environment,
                created_at=now,
                snapshot_id=snapshot.id,
                score_family="employee_overload",
                score=result.score,
                level=None if result.level is None else result.level.value,
                confidence=result.confidence.value,
                scoring_version=result.scoring_model_version,
                factors=[factor.model_dump(mode="json") for factor in result.factors],
                thresholds=result.thresholds,
                evidence_references=list(result.evidence_references),
                missing_evidence=list(result.missing_evidence),
                excluded_evidence=list(result.excluded_evidence),
            )
            session.add(risk)
            await session.flush()
            alert_id: str | None = None
            if result.level is not None:
                alerts = AlertRepository(session)
                if result.level.value == "low":
                    await alerts.resolve_active_risk(
                        environment=self._environment,
                        subject_id=result.subject_id,
                        risk_type="overload",
                    )
                alert = await alerts.record_risk(
                    environment=self._environment,
                    subject_id=result.subject_id,
                    risk_type="overload",
                    scoring_window=input_data.evidence_timestamp.date().isoformat(),
                    risk_result_id=risk.id,
                    level=result.level,
                    evidence_fingerprint=fingerprint,
                    correlation_id=correlation_id,
                    now=now,
                )
                if alert is not None:
                    alert_id = str(alert.alert_id)
        return str(risk.id), alert_id
