from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Literal

import pytest
from sqlalchemy import func, select
from workforce_persistence.database import Database
from workforce_persistence.models import EvidenceSnapshot, RiskResultRecord
from workforce_persistence.repositories import SnapshotRepository
from workforce_risk.evidence.fingerprint import EvidenceFingerprintInput
from workforce_risk.evidence.snapshot import (
    SnapshotRiskResult,
    VersionedEvidenceSnapshot,
)
from workforce_risk.models import ConfidenceLevel, RiskLevel, RiskResult

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)
NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def snapshot(
    environment: Literal["dev", "prod", "test"] = "test",
) -> VersionedEvidenceSnapshot:
    evidence = EvidenceFingerprintInput(
        schema_version="1.0",
        environment=environment,
        subject_id="WRD-SNAPSHOT-1",
        task_state="In Progress",
        current_assignee="synthetic-a",
        employee_workloads={"EMP-001": 32},
        due_date=date(2026, 8, 15),
        dependencies=("WRD-8",),
        scoring_versions=("task-fit-v1",),
        evidence_timestamp=NOW,
    )
    result = RiskResult(
        subject_id="WRD-SNAPSHOT-1",
        environment=environment,
        score=65,
        level=RiskLevel.HIGH,
        confidence=ConfidenceLevel.HIGH,
        scored_at=NOW,
        evidence_timestamp=NOW,
        scoring_model_version="task-fit-v1",
        factors=(),
        thresholds={"low_max": 29, "medium_max": 54, "high_max": 74},
        evidence_references=("jira:WRD-SNAPSHOT-1:status",),
        missing_evidence=(),
        excluded_evidence=(),
    )
    return VersionedEvidenceSnapshot(
        evidence=evidence,
        risk_results=(SnapshotRiskResult(score_family="task_fit", result=result),),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_snapshot_and_complete_results_persist_atomically_and_idempotently() -> (
    None
):
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            repository = SnapshotRepository(session)
            first = await repository.persist(snapshot(), subject_type="task")
            repeated = await repository.persist(snapshot(), subject_type="task")
            assert first == repeated
        async with database.transaction() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(EvidenceSnapshot)
                    .where(
                        EvidenceSnapshot.environment == "test",
                        EvidenceSnapshot.subject_id == "WRD-SNAPSHOT-1",
                        EvidenceSnapshot.fingerprint == snapshot().fingerprint,
                    )
                )
                == 1
            )
            record = await session.scalar(
                select(RiskResultRecord).where(RiskResultRecord.snapshot_id == first)
            )
            assert record is not None
            assert record.evidence_references == ["jira:WRD-SNAPSHOT-1:status"]
            assert record.thresholds["high_max"] == 74
            assert record.scoring_version == "task-fit-v1"
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_snapshot_repository_rejects_environment_mismatch() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            with pytest.raises(ValueError, match="environment"):
                await SnapshotRepository(session).persist(
                    snapshot("dev"), subject_type="task", service_environment="prod"
                )
    finally:
        await database.close()
