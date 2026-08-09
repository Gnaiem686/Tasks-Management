from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from workforce_persistence.database import Database
from workforce_persistence.models import CommentEvidence
from workforce_persistence.repositories import CommentEvidenceRepository
from workforce_risk.comments.classifier import CommentClassifier, load_patterns
from workforce_risk.comments.lifecycle import CommentLifecycleObservation
from workforce_risk.comments.models import (
    AvailabilityStatus,
    CommentEvidenceSignal,
    CommentObservation,
)

ROOT = Path(__file__).parents[2]
DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)
NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def signal(*, updated_at: datetime, retrieved_at: datetime) -> CommentEvidenceSignal:
    classifier = CommentClassifier(
        load_patterns(ROOT / "config/comments/v1.yaml"),
        employee_accounts={"synthetic-account": "EMP-001"},
        manager_accounts=set(),
        reviewer_accounts=set(),
        automation_accounts=set(),
    )
    result = classifier.classify(
        CommentObservation(
            jira_comment_id="comment-lifecycle-1",
            jira_issue_key="WRD-10",
            author_account_id="synthetic-account",
            body="This task is blocked",
            created_at=NOW,
            updated_at=updated_at,
            retrieved_at=retrieved_at,
        )
    )
    assert result.signal is not None
    return result.signal


@pytest.mark.integration
@pytest.mark.asyncio
async def test_edits_and_unavailability_append_immutable_body_free_observations() -> (
    None
):
    database = Database(DATABASE_URL)
    first = CommentLifecycleObservation.from_signal(
        signal(updated_at=NOW, retrieved_at=NOW)
    )
    edited = CommentLifecycleObservation.from_signal(
        signal(
            updated_at=NOW + timedelta(minutes=5),
            retrieved_at=NOW + timedelta(minutes=6),
        )
    )
    unavailable = CommentLifecycleObservation.mark_unavailable(
        edited, retrieved_at=NOW + timedelta(minutes=10)
    )
    try:
        async with database.transaction() as session:
            repository = CommentEvidenceRepository(session)
            first_id = await repository.append(first, environment="test")
            assert await repository.append(first, environment="test") == first_id
            await repository.append(edited, environment="test")
            await repository.append(unavailable, environment="test")
        async with database.transaction() as session:
            records = (
                await session.scalars(
                    select(CommentEvidence)
                    .where(
                        CommentEvidence.environment == "test",
                        CommentEvidence.jira_comment_id == "comment-lifecycle-1",
                    )
                    .order_by(CommentEvidence.retrieved_at)
                )
            ).all()
            assert len(records) == 3
            assert records[0].updated_at == NOW
            assert records[1].updated_at == NOW + timedelta(minutes=5)
            assert records[2].availability_status == AvailabilityStatus.UNAVAILABLE
            assert all("body" not in record.metadata_json for record in records)
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CommentEvidence)
                    .where(
                        CommentEvidence.environment == "test",
                        CommentEvidence.jira_comment_id == "comment-lifecycle-1",
                    )
                )
                == 3
            )
    finally:
        await database.close()
