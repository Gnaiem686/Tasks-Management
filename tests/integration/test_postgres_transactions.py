from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from workforce_persistence.database import Database
from workforce_persistence.models import (
    AuditEvent,
    EmployeeProfile,
    OutboxEvent,
    ReassignmentProposal,
    ScoringVersion,
)
from workforce_persistence.repositories import (
    AuditRepository,
    ProfileRepository,
    ScoringVersionRepository,
)

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_chain_and_outbox_publish_are_transactional_and_retained() -> None:
    database = Database(DATABASE_URL, pool_size=2, max_overflow=0)
    environment = "test"
    run_id = str(uuid.uuid4())
    try:
        async with database.transaction() as session:
            audit = AuditRepository(session)
            await audit.append(
                environment=environment,
                action_type="alert.created",
                actor_type="system",
                actor_id="scan-worker",
                subject_ids=["EMP-002"],
                correlation_id=f"corr-postgres-{run_id}",
            )
            session.add(
                OutboxEvent(
                    id=uuid.uuid4(),
                    environment=environment,
                    created_at=datetime.now(UTC),
                    consumer_key=f"{environment}:alert-{run_id}",
                    event_type="alert.created",
                    payload={"alert_id": "synthetic-alert"},
                    delivery_attempts=1,
                    published_at=datetime.now(UTC),
                )
            )
        async with database.transaction() as session:
            assert await AuditRepository(session).verify_chain(environment)
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(
                        OutboxEvent.environment == environment,
                        OutboxEvent.consumer_key == f"{environment}:alert-{run_id}",
                        OutboxEvent.published_at.is_not(None),
                    )
                )
                == 1
            )
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_proposal_idempotency_and_profile_optimistic_version() -> None:
    database = Database(DATABASE_URL, pool_size=2, max_overflow=0)
    unique = str(uuid.uuid4())
    profile_id = uuid.uuid4()
    now = datetime.now(UTC)
    try:
        async with database.transaction() as session:
            session.add(
                EmployeeProfile(
                    id=profile_id,
                    environment="test",
                    created_at=now,
                    employee_id=f"TEST-{unique[:20]}",
                    role="Engineer",
                    seniority="mid",
                    weekly_capacity_hours=40,
                    mentoring_available=False,
                    version=1,
                )
            )
        with pytest.raises(IntegrityError):
            async with database.transaction() as session:
                for proposal_id in (uuid.uuid4(), uuid.uuid4()):
                    session.add(
                        ReassignmentProposal(
                            id=proposal_id,
                            environment="test",
                            created_at=now,
                            task_key=f"WRD-{unique}",
                            expected_assignee="synthetic-a",
                            proposed_assignee="synthetic-b",
                            state="pending",
                            idempotency_key=f"proposal-{unique}",
                            evidence_fingerprint="fingerprint",
                            expires_at=now,
                            version=1,
                        )
                    )
                await session.flush()
        async with database.transaction() as session:
            updated = await ProfileRepository(session).update_capacity(
                profile_id=profile_id, expected_version=1, capacity_hours=32
            )
            stale = await ProfileRepository(session).update_capacity(
                profile_id=profile_id, expected_version=1, capacity_hours=20
            )
            assert updated is True
            assert stale is False
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scoring_activation_is_one_way_and_immutable() -> None:
    database = Database(DATABASE_URL, pool_size=2, max_overflow=0)
    version_id = uuid.uuid4()
    try:
        async with database.transaction() as session:
            session.add(
                ScoringVersion(
                    id=version_id,
                    environment="test",
                    created_at=datetime.now(UTC),
                    version=f"test-{version_id}",
                    configuration={"weights": {"utilization": 1.0}},
                )
            )
        async with database.transaction() as session:
            repository = ScoringVersionRepository(session)
            assert await repository.activate(version_id, actor_id="admin-1") is True
            assert await repository.activate(version_id, actor_id="admin-2") is False
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_chain_detects_tampered_metadata() -> None:
    database = Database(DATABASE_URL, pool_size=2, max_overflow=0)
    environment = "tamper-test"
    correlation_id = f"corr-tamper-{uuid.uuid4()}"
    try:
        async with database.transaction() as session:
            event = await AuditRepository(session).append(
                environment=environment,
                action_type="profile.updated",
                actor_type="administrator",
                actor_id="admin-test",
                subject_ids=["EMP-001"],
                correlation_id=correlation_id,
                safe_metadata={"field": "capacity"},
            )
            await session.flush()
            event_id = event.id
        async with database.transaction() as session:
            await session.execute(
                update(AuditEvent)
                .where(AuditEvent.id == event_id)
                .values(safe_metadata={"field": "tampered"})
            )
        async with database.transaction() as session:
            assert await AuditRepository(session).verify_chain(environment) is False
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_transaction_rolls_back_audit_and_business_state() -> None:
    database = Database(DATABASE_URL, pool_size=2, max_overflow=0)
    environment = "test"
    correlation_id = f"corr-rollback-{uuid.uuid4()}"
    try:
        with pytest.raises(RuntimeError, match="simulated approval failure"):
            async with database.transaction() as session:
                await AuditRepository(session).append(
                    environment=environment,
                    action_type="proposal.approved",
                    actor_type="manager",
                    actor_id="synthetic-manager",
                    subject_ids=["proposal-1"],
                    correlation_id=correlation_id,
                )
                raise RuntimeError("simulated approval failure")
        async with database.transaction() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.environment == environment,
                        AuditEvent.correlation_id == correlation_id,
                    )
                )
                == 0
            )
    finally:
        await database.close()
