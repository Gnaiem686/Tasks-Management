from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class CommentCategory(StrEnum):
    TEMPORARY_UNAVAILABILITY_REPORT = "temporary_unavailability_report"
    CLARIFICATION_REQUEST = "clarification_request"
    TECHNICAL_HELP_REQUEST = "technical_help_request"
    BLOCKER_REPORT = "blocker_report"
    REVIEW_WAITING_REPORT = "review_waiting_report"
    WORKLOAD_CONCERN = "workload_concern"
    DEADLINE_CONCERN = "deadline_concern"
    MISSING_ACCESS_REPORT = "missing_access_report"
    TASK_FRUSTRATION_REPORT = "task_frustration_report"
    COLLABORATION_CONCERN = "collaboration_concern"


class AuthorType(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    REVIEWER = "reviewer"
    AUTOMATION = "automation"
    UNMAPPED = "unmapped"


class AttributionStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class FreshnessStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class AvailabilityWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def validate_order(self) -> AvailabilityWindow:
        if self.ends_at <= self.starts_at:
            raise ValueError("availability window must end after it starts")
        return self


class CommentObservation(BaseModel):
    """Transient Jira input; its body must never be persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    jira_comment_id: str = Field(min_length=1, max_length=128)
    jira_issue_key: str = Field(min_length=1, max_length=64)
    author_account_id: str | None = Field(default=None, max_length=256)
    body: str = Field(min_length=1, max_length=10_000)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    retrieved_at: AwareDatetime
    availability_window: AvailabilityWindow | None = None


class CommentEvidenceSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1.0"
    classifier_version: str
    category: CommentCategory
    jira_comment_id: str
    jira_issue_key: str
    author_reference: str
    author_type: AuthorType
    attribution_status: AttributionStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    retrieved_at: AwareDatetime
    freshness: FreshnessStatus
    availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE
    availability_window: AvailabilityWindow | None = None
    extraction_confidence: str = "high"
    report_only: bool = True
    scoring_eligible: bool = False
    candidate_eligible: bool = False
    proposal_evidence_eligible: bool = False
    time_bounded_impact_allowed: bool = False


class CommentClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    signal: CommentEvidenceSignal | None
    author_type: AuthorType
    attribution_status: AttributionStatus
    reason: str
