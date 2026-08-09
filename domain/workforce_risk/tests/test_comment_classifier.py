from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from workforce_risk.comments.classifier import CommentClassifier, load_patterns
from workforce_risk.comments.models import (
    AttributionStatus,
    AuthorType,
    CommentObservation,
)

ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def observation(
    body: str, account_id: str | None = "account-employee"
) -> CommentObservation:
    return CommentObservation(
        jira_comment_id="comment-1",
        jira_issue_key="WRD-10",
        author_account_id=account_id,
        body=body,
        created_at=NOW,
        updated_at=NOW,
        retrieved_at=NOW,
    )


def classifier() -> CommentClassifier:
    return CommentClassifier(
        load_patterns(ROOT / "config/comments/v1.yaml"),
        employee_accounts={"account-employee": "EMP-001"},
        manager_accounts={"account-manager"},
        reviewer_accounts={"account-reviewer"},
        automation_accounts={"account-bot"},
    )


@pytest.mark.unit
def test_all_twelve_source_situations_map_to_ten_author_independent_categories() -> (
    None
):
    fixtures = json.loads(
        (ROOT / "tests/fixtures/comments/source_situations.json").read_text()
    )
    actual = []
    for fixture in fixtures:
        result = classifier().classify(observation(fixture["body"]))
        assert result.signal is not None
        assert result.signal.category.value == fixture["category"]
        assert result.signal.report_only is True
        assert result.signal.scoring_eligible is False
        assert result.signal.proposal_evidence_eligible is False
        assert "body" not in result.signal.model_dump()
        actual.append(result.signal.category.value)
    assert len(fixtures) == 12
    assert len(set(actual)) == 10


@pytest.mark.unit
@pytest.mark.parametrize(
    ("account_id", "author_type", "reference"),
    [
        ("account-employee", AuthorType.EMPLOYEE, "EMP-001"),
        ("account-manager", AuthorType.MANAGER, "account-manager"),
        ("account-reviewer", AuthorType.REVIEWER, "account-reviewer"),
        ("account-bot", AuthorType.AUTOMATION, "account-bot"),
    ],
)
def test_category_is_independent_of_validated_author_type(
    account_id: str, author_type: AuthorType, reference: str
) -> None:
    result = classifier().classify(observation("This task is blocked", account_id))
    assert result.signal is not None
    assert result.signal.author_type is author_type
    assert result.signal.author_reference == reference
    assert result.signal.attribution_status is AttributionStatus.VERIFIED


@pytest.mark.unit
def test_unmapped_or_missing_author_and_ambiguous_text_produce_no_signal() -> None:
    for account_id in (None, "unknown-account"):
        result = classifier().classify(observation("This task is blocked", account_id))
        assert result.signal is None
        assert result.author_type is AuthorType.UNMAPPED
        assert result.attribution_status is AttributionStatus.UNVERIFIED
    ambiguous = json.loads(
        (ROOT / "tests/fixtures/comments/ambiguous_cases.json").read_text()
    )
    assert all(
        classifier().classify(observation(text)).signal is None for text in ambiguous
    )


@pytest.mark.unit
def test_only_temporary_unavailability_impact_requires_explicit_window() -> None:
    unavailable = classifier().classify(observation("I will be unavailable tomorrow"))
    clarification = classifier().classify(observation("I need clarification"))
    assert unavailable.signal is not None
    assert unavailable.signal.availability_window is None
    assert unavailable.signal.time_bounded_impact_allowed is False
    assert clarification.signal is not None
    assert clarification.signal.availability_window is None
