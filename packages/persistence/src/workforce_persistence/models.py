from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RecordMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    environment: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ApiKeyPrincipal(RecordMixin, Base):
    __tablename__ = "api_key_principals"
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_label: Mapped[str] = mapped_column(String(128), nullable=False)
    key_digest: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    project_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmployeeProfile(RecordMixin, Base):
    __tablename__ = "employee_profiles"
    employee_id: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    seniority: Mapped[str] = mapped_column(String(64), nullable=False)
    weekly_capacity_hours: Mapped[float] = mapped_column(Float, nullable=False)
    mentoring_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    jira_account_id: Mapped[str | None] = mapped_column(String(256))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        UniqueConstraint("environment", "employee_id", name="uq_profiles_env_employee"),
    )


class EmployeeSkill(RecordMixin, Base):
    __tablename__ = "employee_skills"
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employee_profiles.id"))
    skill: Mapped[str] = mapped_column(String(128), nullable=False)
    proficiency: Mapped[int] = mapped_column(Integer, nullable=False)


class CapacityAllocation(RecordMixin, Base):
    __tablename__ = "capacity_allocations"
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employee_profiles.id"))
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    allocation_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CapacityOverride(RecordMixin, Base):
    __tablename__ = "capacity_overrides"
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employee_profiles.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity_hours: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)


class ScoringVersion(RecordMixin, Base):
    __tablename__ = "scoring_versions"
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (
        UniqueConstraint("environment", "version", name="uq_scoring_env_version"),
    )


class EvidenceSnapshot(RecordMixin, Base):
    __tablename__ = "evidence_snapshots"
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "subject_type",
            "subject_id",
            "fingerprint",
            name="uq_evidence_snapshot_identity",
        ),
    )


class RiskResultRecord(RecordMixin, Base):
    __tablename__ = "risk_results"
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_snapshots.id"))
    score_family: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    level: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(128), nullable=False)
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    thresholds: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    evidence_references: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    missing_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    excluded_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class CommentEvidence(RecordMixin, Base):
    __tablename__ = "comment_evidence"
    jira_comment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    jira_issue_key: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    author_reference: Mapped[str | None] = mapped_column(String(256))
    author_type: Mapped[str] = mapped_column(String(32), nullable=False)
    attribution_status: Mapped[str] = mapped_column(String(32), nullable=False)
    comment_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    freshness: Mapped[str] = mapped_column(String(32), nullable=False)
    availability_status: Mapped[str] = mapped_column(String(32), nullable=False)
    observation_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "jira_comment_id",
            "observation_fingerprint",
            name="uq_comment_evidence_observation",
        ),
    )


class WorkWeek(RecordMixin, Base):
    __tablename__ = "work_weeks"
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "project_key",
            "week_start",
            name="uq_work_week_env_project_start",
        ),
    )


class TaskCurrentState(RecordMixin, Base):
    __tablename__ = "task_current_states"
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_key: Mapped[str] = mapped_column(String(64), nullable=False)
    work_week_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_weeks.id"))
    evidence_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    jira_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_structured_progress_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "project_key",
            "issue_key",
            name="uq_task_current_env_project_issue",
        ),
    )


class TaskProgressSnapshot(RecordMixin, Base):
    __tablename__ = "task_progress_snapshots"
    work_week_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_weeks.id"))
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_key: Mapped[str] = mapped_column(String(64), nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(String(256))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    jira_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(128), nullable=False)
    original_estimate_hours: Mapped[float | None] = mapped_column(Float)
    remaining_estimate_hours: Mapped[float | None] = mapped_column(Float)
    time_spent_hours: Mapped[float | None] = mapped_column(Float)
    due_date: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[str | None] = mapped_column(String(64))
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blocker_issue_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="jira")
    evidence_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "project_key",
            "issue_key",
            "work_week_id",
            "evidence_fingerprint",
            name="uq_task_snapshot_env_issue_week_fingerprint",
        ),
    )


class TaskProgressEvent(RecordMixin, Base):
    __tablename__ = "task_progress_events"
    work_week_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_weeks.id"))
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_key: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_id: Mapped[str | None] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    old_value: Mapped[Any | None] = mapped_column(JSON)
    new_value: Mapped[Any | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="jira")
    event_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "event_fingerprint",
            name="uq_task_progress_event_env_fingerprint",
        ),
    )


class ReassignmentProposal(RecordMixin, Base):
    __tablename__ = "reassignment_proposals"
    simulation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    task_key: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_assignee: Mapped[str] = mapped_column(String(256), nullable=False)
    proposed_assignee: Mapped[str] = mapped_column(String(256), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    scoring_versions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    simulation_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','approved','executing','executed_verified',"
            "'execution_failed','uncertain','rejected','expired','stale')",
            name="ck_reassignment_proposals_state",
        ),
        UniqueConstraint(
            "environment",
            "idempotency_key",
            name="uq_reassignment_proposals_environment_idempotency",
        ),
    )


class ReassignmentSimulation(RecordMixin, Base):
    __tablename__ = "reassignment_simulations"
    simulation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    task_key: Mapped[str] = mapped_column(String(64), nullable=False)
    current_assignee: Mapped[str] = mapped_column(String(256), nullable=False)
    proposed_assignee: Mapped[str] = mapped_column(String(256), nullable=False)
    candidate_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    scoring_versions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    safe_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint("environment", "simulation_id", name="uq_simulation_env_id"),
    )


class ApprovalDecision(RecordMixin, Base):
    __tablename__ = "approval_decisions"
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reassignment_proposals.id")
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "environment", "idempotency_key", name="uq_decision_env_idempotency"
        ),
    )


class ProposalExecution(RecordMixin, Base):
    __tablename__ = "proposal_executions"
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reassignment_proposals.id")
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    external_correlation_id: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    write_attempted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "environment", "proposal_id", name="uq_execution_env_proposal"
        ),
    )


class Alert(RecordMixin, Base):
    __tablename__ = "alerts"
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scoring_window: Mapped[str] = mapped_column(String(64), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        UniqueConstraint("environment", "dedup_key", name="uq_alerts_env_dedup"),
    )


class AlertOccurrence(RecordMixin, Base):
    __tablename__ = "alert_occurrences"
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id"))
    risk_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_results.id"))
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)


class ReportMetadata(RecordMixin, Base):
    __tablename__ = "report_metadata"
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(1024))
    object_version: Mapped[str | None] = mapped_column(String(256))
    checksum: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "environment", "idempotency_key", name="uq_reports_env_idempotency"
        ),
    )


class ScanRun(RecordMixin, Base):
    __tablename__ = "scan_runs"
    scope: Mapped[str] = mapped_column(String(256), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued','running','completed','completed_degraded',"
            "'failed','skipped_duplicate')",
            name="ck_scan_runs_state",
        ),
        UniqueConstraint(
            "environment",
            "idempotency_key",
            name="uq_scan_runs_environment_idempotency",
        ),
    )


class OutboxEvent(RecordMixin, Base):
    __tablename__ = "outbox_events"
    consumer_key: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint(
            "environment", "consumer_key", name="uq_outbox_events_consumer_key"
        ),
    )


class NotificationDelivery(RecordMixin, Base):
    __tablename__ = "notification_deliveries"
    consumer_key: Mapped[str] = mapped_column(String(256), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','sending','sent','retrying','failed')",
            name="ck_notification_deliveries_state",
        ),
        UniqueConstraint(
            "environment", "consumer_key", name="uq_delivery_env_consumer"
        ),
    )


class AuditEvent(RecordMixin, Base):
    __tablename__ = "audit_events"
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(128))
    event_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    prior_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "environment", "sequence_number", name="uq_audit_env_sequence"
        ),
        UniqueConstraint("environment", "event_hash", name="uq_audit_env_hash"),
    )
