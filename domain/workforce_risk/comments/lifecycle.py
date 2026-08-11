from __future__ import annotations

import hashlib
import json

from pydantic import AwareDatetime, BaseModel, ConfigDict

from workforce_risk.comments.models import (
    AttributionStatus,
    AuthorType,
    AvailabilityStatus,
    AvailabilityWindow,
    CommentCategory,
    CommentEvidenceSignal,
    FreshnessStatus,
)


class CommentLifecycleObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str
    classifier_version: str
    category: CommentCategory
    jira_comment_id: str
    jira_issue_key: str
    author_reference: str
    author_type: AuthorType
    attribution_status: AttributionStatus
    comment_created_at: AwareDatetime
    updated_at: AwareDatetime
    retrieved_at: AwareDatetime
    freshness: FreshnessStatus
    availability_status: AvailabilityStatus
    availability_window: AvailabilityWindow | None
    report_only: bool = True
    scoring_eligible: bool = False
    candidate_eligible: bool = False
    proposal_evidence_eligible: bool = False

    @classmethod
    def from_signal(cls, signal: CommentEvidenceSignal) -> CommentLifecycleObservation:
        return cls(
            schema_version=signal.schema_version,
            classifier_version=signal.classifier_version,
            category=signal.category,
            jira_comment_id=signal.jira_comment_id,
            jira_issue_key=signal.jira_issue_key,
            author_reference=signal.author_reference,
            author_type=signal.author_type,
            attribution_status=signal.attribution_status,
            comment_created_at=signal.created_at,
            updated_at=signal.updated_at,
            retrieved_at=signal.retrieved_at,
            freshness=signal.freshness,
            availability_status=signal.availability_status,
            availability_window=signal.availability_window,
        )

    @classmethod
    def mark_unavailable(
        cls,
        previous: CommentLifecycleObservation,
        *,
        retrieved_at: AwareDatetime,
    ) -> CommentLifecycleObservation:
        return previous.model_copy(
            update={
                "retrieved_at": retrieved_at,
                "freshness": FreshnessStatus.STALE,
                "availability_status": AvailabilityStatus.UNAVAILABLE,
            }
        )

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
