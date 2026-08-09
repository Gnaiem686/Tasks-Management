from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from workforce_risk.comments.models import (
    AttributionStatus,
    AuthorType,
    CommentCategory,
    CommentClassificationResult,
    CommentEvidenceSignal,
    CommentObservation,
    FreshnessStatus,
)


class PatternConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str
    categories: dict[CommentCategory, tuple[str, ...]]
    disqualifiers: tuple[str, ...]


def load_patterns(path: Path) -> PatternConfiguration:
    return PatternConfiguration.model_validate(yaml.safe_load(path.read_text()))


class CommentClassifier:
    def __init__(
        self,
        patterns: PatternConfiguration,
        *,
        employee_accounts: dict[str, str],
        manager_accounts: set[str],
        reviewer_accounts: set[str],
        automation_accounts: set[str],
    ) -> None:
        self._patterns = patterns
        self._employees = employee_accounts
        self._managers = manager_accounts
        self._reviewers = reviewer_accounts
        self._automation = automation_accounts

    def _author(self, account_id: str | None) -> tuple[AuthorType, str | None]:
        if account_id in self._employees:
            assert account_id is not None
            return AuthorType.EMPLOYEE, self._employees[account_id]
        if account_id in self._managers:
            return AuthorType.MANAGER, account_id
        if account_id in self._reviewers:
            return AuthorType.REVIEWER, account_id
        if account_id in self._automation:
            return AuthorType.AUTOMATION, account_id
        return AuthorType.UNMAPPED, account_id

    def classify(self, observation: CommentObservation) -> CommentClassificationResult:
        author_type, author_reference = self._author(observation.author_account_id)
        if author_type is AuthorType.UNMAPPED or author_reference is None:
            return CommentClassificationResult(
                signal=None,
                author_type=AuthorType.UNMAPPED,
                attribution_status=AttributionStatus.UNVERIFIED,
                reason="author is missing or not mapped",
            )
        normalized = " ".join(observation.body.casefold().split())
        if any(term.casefold() in normalized for term in self._patterns.disqualifiers):
            return CommentClassificationResult(
                signal=None,
                author_type=author_type,
                attribution_status=AttributionStatus.VERIFIED,
                reason="comment is ambiguous or contains untrusted instructions",
            )
        matches = {
            category
            for category, phrases in self._patterns.categories.items()
            if any(phrase.casefold() in normalized for phrase in phrases)
        }
        if len(matches) != 1:
            return CommentClassificationResult(
                signal=None,
                author_type=author_type,
                attribution_status=AttributionStatus.VERIFIED,
                reason="no single explicit configured category",
            )
        category = matches.pop()
        window = (
            observation.availability_window
            if category is CommentCategory.TEMPORARY_UNAVAILABILITY_REPORT
            else None
        )
        freshness = (
            FreshnessStatus.CURRENT
            if observation.retrieved_at - observation.updated_at <= timedelta(hours=24)
            else FreshnessStatus.STALE
        )
        signal = CommentEvidenceSignal(
            classifier_version=self._patterns.version,
            category=category,
            jira_comment_id=observation.jira_comment_id,
            jira_issue_key=observation.jira_issue_key,
            author_reference=author_reference,
            author_type=author_type,
            attribution_status=AttributionStatus.VERIFIED,
            created_at=observation.created_at,
            updated_at=observation.updated_at,
            retrieved_at=observation.retrieved_at,
            freshness=freshness,
            availability_window=window,
            time_bounded_impact_allowed=window is not None,
        )
        return CommentClassificationResult(
            signal=signal,
            author_type=author_type,
            attribution_status=AttributionStatus.VERIFIED,
            reason="one explicit configured category matched",
        )
