from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from workforce_persistence.alert_repository import AlertRepository
from workforce_persistence.database import Database
from workforce_persistence.models import (
    Alert,
    AlertOccurrence,
    EvidenceSnapshot,
    OutboxEvent,
    RiskResultRecord,
)
from workforce_risk.alerts.state import AlertState
from workforce_risk.models import RiskLevel

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)


async def create_risk(session: object, marker: str) -> uuid.UUID:
    now = datetime.now(UTC)
    snapshot = EvidenceSnapshot(
        id=uuid.uuid4(),
        environment="test",
        created_at=now,
        subject_type="employee",
        subject_id=marker,
        fingerprint=marker,
        evidence={},
        observed_at=now,
    )
    risk = RiskResultRecord(
        id=uuid.uuid4(),
        environment="test",
        created_at=now,
        snapshot_id=snapshot.id,
        score_family="employee_overload",
        score=80,
        level="critical",
        confidence="high",
        scoring_version="v1",
        factors=[],
        thresholds={},
        evidence_references=[],
        missing_evidence=[],
        excluded_evidence=[],
    )
    session.add_all([snapshot, risk])  # type: ignore[attr-defined]
    await session.flush()  # type: ignore[attr-defined]
    return risk.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_alert_occurrence_and_outbox_are_atomic_and_deduplicated() -> None:
    database = Database(DATABASE_URL)
    marker = f"atomic-{uuid.uuid4()}"
    try:
        async with database.transaction() as session:
            risk_id = await create_risk(session, marker)
            repository = AlertRepository(session)
            first = await repository.record_risk(
                environment="test",
                subject_id=marker,
                risk_type="overload",
                scoring_window="2026-08-09",
                risk_result_id=risk_id,
                level=RiskLevel.CRITICAL,
                evidence_fingerprint="evidence-1",
                correlation_id="corr-alert",
                now=datetime.now(UTC),
            )
            repeated = await repository.record_risk(
                environment="test",
                subject_id=marker,
                risk_type="overload",
                scoring_window="2026-08-09",
                risk_result_id=risk_id,
                level=RiskLevel.CRITICAL,
                evidence_fingerprint="evidence-1",
                correlation_id="corr-alert",
                now=datetime.now(UTC),
            )
            assert first is not None and first.notification_created
            assert repeated is not None and not repeated.occurrence_created
        async with database.transaction() as session:
            alert = await session.scalar(
                select(Alert).where(Alert.subject_id == marker)
            )
            assert alert is not None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AlertOccurrence)
                    .where(AlertOccurrence.alert_id == alert.id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(
                        OutboxEvent.environment == "test",
                        OutboxEvent.payload["alert_id"].as_string() == str(alert.id),
                    )
                )
                == 1
            )
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dismissal_is_audited_and_etag_conflict_is_rejected() -> None:
    database = Database(DATABASE_URL)
    marker = f"dismiss-{uuid.uuid4()}"
    try:
        async with database.transaction() as session:
            risk_id = await create_risk(session, marker)
            repository = AlertRepository(session)
            recorded = await repository.record_risk(
                environment="test",
                subject_id=marker,
                risk_type="overload",
                scoring_window="2026-08-09",
                risk_result_id=risk_id,
                level=RiskLevel.HIGH,
                evidence_fingerprint="evidence-1",
                correlation_id="corr-alert",
                now=datetime.now(UTC),
            )
            assert recorded is not None
            assert await repository.transition(
                alert_id=recorded.alert_id,
                expected_version=recorded.version,
                target=AlertState.DISMISSED,
                actor_id="manager-safe",
                correlation_id="corr-dismiss",
                dismissal_reason="Planned spike",
            )
            assert not await repository.transition(
                alert_id=recorded.alert_id,
                expected_version=recorded.version,
                target=AlertState.RESOLVED,
                actor_id="manager-safe",
                correlation_id="corr-stale",
            )
    finally:
        await database.close()
