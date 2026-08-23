from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from workforce_persistence.models import (
    AuditEvent,
    CapacityAllocation,
    CapacityOverride,
    CommentEvidence,
    EmployeeProfile,
    EmployeeSkill,
    EvidenceSnapshot,
    RiskResultRecord,
    ScoringVersion,
)

if TYPE_CHECKING:
    from workforce_risk.comments.lifecycle import CommentLifecycleObservation
    from workforce_risk.evidence.snapshot import VersionedEvidenceSnapshot


@dataclass(frozen=True)
class StoredProfile:
    id: uuid.UUID
    environment: str
    employee_id: str
    role: str
    seniority: str
    weekly_capacity_hours: float
    mentoring_available: bool
    jira_account_id: str | None
    version: int
    skills: tuple[tuple[str, int], ...]
    allocations: tuple[tuple[str, float], ...]
    capacity_overrides: tuple[tuple[datetime, datetime, float, str], ...]


class ProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        environment: str,
        employee_id: str,
        role: str,
        seniority: str,
        weekly_capacity_hours: float,
        mentoring_available: bool,
        jira_account_id: str | None,
        skills: tuple[tuple[str, int], ...],
        allocations: tuple[tuple[str, float], ...],
        capacity_overrides: tuple[tuple[datetime, datetime, float, str], ...],
        actor_id: str,
        correlation_id: str,
        created_at: datetime,
    ) -> StoredProfile:
        profile = EmployeeProfile(
            id=uuid.uuid4(),
            environment=environment,
            created_at=created_at,
            employee_id=employee_id,
            role=role,
            seniority=seniority,
            weekly_capacity_hours=weekly_capacity_hours,
            mentoring_available=mentoring_available,
            jira_account_id=jira_account_id,
            version=1,
        )
        self._session.add(profile)
        await self._session.flush()
        self._session.add_all(
            [
                EmployeeSkill(
                    id=uuid.uuid4(),
                    environment=environment,
                    created_at=created_at,
                    profile_id=profile.id,
                    skill=name,
                    proficiency=proficiency,
                )
                for name, proficiency in skills
            ]
            + [
                CapacityAllocation(
                    id=uuid.uuid4(),
                    environment=environment,
                    created_at=created_at,
                    profile_id=profile.id,
                    project_key=project_key,
                    allocation_fraction=fraction,
                    effective_from=created_at,
                )
                for project_key, fraction in allocations
            ]
            + [
                CapacityOverride(
                    id=uuid.uuid4(),
                    environment=environment,
                    created_at=created_at,
                    profile_id=profile.id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    capacity_hours=capacity,
                    reason=reason,
                )
                for starts_at, ends_at, capacity, reason in capacity_overrides
            ]
        )
        await AuditRepository(self._session).append(
            environment=environment,
            action_type="profile.created",
            actor_type="administrator",
            actor_id=actor_id,
            subject_ids=[employee_id],
            correlation_id=correlation_id,
            new_state={"version": 1},
        )
        return await self._load(profile)

    async def get(self, *, environment: str, employee_id: str) -> StoredProfile | None:
        profile = await self._session.scalar(
            select(EmployeeProfile).where(
                EmployeeProfile.environment == environment,
                EmployeeProfile.employee_id == employee_id,
            )
        )
        return None if profile is None else await self._load(profile)

    async def list_for_environment(
        self, *, environment: str
    ) -> tuple[StoredProfile, ...]:
        profiles = (
            await self._session.scalars(
                select(EmployeeProfile)
                .where(EmployeeProfile.environment == environment)
                .order_by(EmployeeProfile.employee_id)
            )
        ).all()
        return tuple([await self._load(profile) for profile in profiles])

    async def _load(self, profile: EmployeeProfile) -> StoredProfile:
        skills = (
            await self._session.execute(
                select(EmployeeSkill.skill, EmployeeSkill.proficiency)
                .where(EmployeeSkill.profile_id == profile.id)
                .order_by(EmployeeSkill.skill)
            )
        ).all()
        allocations = (
            await self._session.execute(
                select(
                    CapacityAllocation.project_key,
                    CapacityAllocation.allocation_fraction,
                )
                .where(CapacityAllocation.profile_id == profile.id)
                .order_by(CapacityAllocation.project_key)
            )
        ).all()
        overrides = (
            await self._session.execute(
                select(
                    CapacityOverride.starts_at,
                    CapacityOverride.ends_at,
                    CapacityOverride.capacity_hours,
                    CapacityOverride.reason,
                )
                .where(CapacityOverride.profile_id == profile.id)
                .order_by(CapacityOverride.starts_at)
            )
        ).all()
        return StoredProfile(
            id=profile.id,
            environment=profile.environment,
            employee_id=profile.employee_id,
            role=profile.role,
            seniority=profile.seniority,
            weekly_capacity_hours=profile.weekly_capacity_hours,
            mentoring_available=profile.mentoring_available,
            jira_account_id=profile.jira_account_id,
            version=profile.version,
            skills=tuple((row.skill, row.proficiency) for row in skills),
            allocations=tuple(
                (row.project_key, row.allocation_fraction) for row in allocations
            ),
            capacity_overrides=tuple(
                (row.starts_at, row.ends_at, row.capacity_hours, row.reason)
                for row in overrides
            ),
        )

    async def update_capacity_audited(
        self,
        *,
        environment: str,
        employee_id: str,
        expected_version: int,
        capacity_hours: float,
        actor_id: str,
        correlation_id: str,
    ) -> StoredProfile | None:
        profile = await self._session.scalar(
            select(EmployeeProfile).where(
                EmployeeProfile.environment == environment,
                EmployeeProfile.employee_id == employee_id,
            )
        )
        if profile is None:
            return None
        prior_capacity = profile.weekly_capacity_hours
        if not await self.update_capacity(
            profile_id=profile.id,
            expected_version=expected_version,
            capacity_hours=capacity_hours,
        ):
            return None
        await AuditRepository(self._session).append(
            environment=environment,
            action_type="profile.updated",
            actor_type="administrator",
            actor_id=actor_id,
            subject_ids=[employee_id],
            correlation_id=correlation_id,
            prior_state={"version": expected_version, "capacity": prior_capacity},
            new_state={"version": expected_version + 1, "capacity": capacity_hours},
        )
        await self._session.refresh(profile)
        return await self._load(profile)

    async def update_capacity(
        self, *, profile_id: uuid.UUID, expected_version: int, capacity_hours: float
    ) -> bool:
        result = await self._session.execute(
            update(EmployeeProfile)
            .where(
                EmployeeProfile.id == profile_id,
                EmployeeProfile.version == expected_version,
            )
            .values(
                weekly_capacity_hours=capacity_hours,
                version=EmployeeProfile.version + 1,
            )
        )
        return cast(CursorResult[Any], result).rowcount == 1


class ScoringVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def activate(self, version_id: uuid.UUID, *, actor_id: str) -> bool:
        result = await self._session.execute(
            update(ScoringVersion)
            .where(
                ScoringVersion.id == version_id,
                ScoringVersion.activated_at.is_(None),
            )
            .values(activated_at=datetime.now(UTC), activated_by=actor_id)
        )
        return cast(CursorResult[Any], result).rowcount == 1


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist(
        self,
        snapshot: VersionedEvidenceSnapshot,
        *,
        subject_type: str,
        service_environment: str | None = None,
    ) -> uuid.UUID:
        evidence = snapshot.evidence
        if (
            service_environment is not None
            and evidence.environment != service_environment
        ):
            raise ValueError("snapshot environment mismatch")
        existing = await self._session.scalar(
            select(EvidenceSnapshot).where(
                EvidenceSnapshot.environment == evidence.environment,
                EvidenceSnapshot.subject_type == subject_type,
                EvidenceSnapshot.subject_id == evidence.subject_id,
                EvidenceSnapshot.fingerprint == snapshot.fingerprint,
            )
        )
        if existing is not None:
            return existing.id
        record = EvidenceSnapshot(
            id=uuid.uuid4(),
            environment=evidence.environment,
            created_at=datetime.now(UTC),
            subject_type=subject_type,
            subject_id=evidence.subject_id,
            fingerprint=snapshot.fingerprint,
            evidence={
                **evidence.canonical_material(),
                "evidence_timestamp": evidence.evidence_timestamp.isoformat(),
            },
            observed_at=evidence.evidence_timestamp,
        )
        self._session.add(record)
        await self._session.flush()
        for snapshot_result in snapshot.risk_results:
            result = snapshot_result.result
            self._session.add(
                RiskResultRecord(
                    id=uuid.uuid4(),
                    environment=evidence.environment,
                    created_at=datetime.now(UTC),
                    snapshot_id=record.id,
                    score_family=snapshot_result.score_family,
                    score=result.score,
                    level=None if result.level is None else result.level.value,
                    confidence=result.confidence.value,
                    scoring_version=result.scoring_model_version,
                    factors=[
                        factor.model_dump(mode="json") for factor in result.factors
                    ],
                    thresholds=result.thresholds,
                    evidence_references=list(result.evidence_references),
                    missing_evidence=list(result.missing_evidence),
                    excluded_evidence=list(result.excluded_evidence),
                )
            )
        return record.id


class CommentEvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self, observation: CommentLifecycleObservation, *, environment: str
    ) -> uuid.UUID:
        fingerprint = observation.fingerprint()
        existing = await self._session.scalar(
            select(CommentEvidence).where(
                CommentEvidence.environment == environment,
                CommentEvidence.jira_comment_id == observation.jira_comment_id,
                CommentEvidence.observation_fingerprint == fingerprint,
            )
        )
        if existing is not None:
            return existing.id
        record = CommentEvidence(
            id=uuid.uuid4(),
            environment=environment,
            created_at=datetime.now(UTC),
            jira_comment_id=observation.jira_comment_id,
            jira_issue_key=observation.jira_issue_key,
            category=observation.category.value,
            author_reference=observation.author_reference,
            author_type=observation.author_type.value,
            attribution_status=observation.attribution_status.value,
            comment_created_at=observation.comment_created_at,
            updated_at=observation.updated_at,
            retrieved_at=observation.retrieved_at,
            freshness=observation.freshness.value,
            availability_status=observation.availability_status.value,
            observation_fingerprint=fingerprint,
            metadata_json={
                "schema_version": observation.schema_version,
                "classifier_version": observation.classifier_version,
                "availability_window": (
                    None
                    if observation.availability_window is None
                    else observation.availability_window.model_dump(mode="json")
                ),
                "report_only": True,
                "scoring_eligible": False,
                "candidate_eligible": False,
                "proposal_evidence_eligible": False,
            },
        )
        self._session.add(record)
        await self._session.flush()
        return record.id


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _event_hash(payload: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def append(
        self,
        *,
        environment: str,
        action_type: str,
        actor_type: str,
        actor_id: str,
        subject_ids: list[str],
        correlation_id: str,
        prior_state: dict[str, Any] | None = None,
        new_state: dict[str, Any] | None = None,
        safe_metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        latest = await self._session.scalar(
            select(AuditEvent)
            .where(AuditEvent.environment == environment)
            .order_by(AuditEvent.sequence_number.desc())
            .limit(1)
        )
        sequence = 1 if latest is None else latest.sequence_number + 1
        previous_hash = None if latest is None else latest.event_hash
        payload = {
            "sequence": sequence,
            "previous_hash": previous_hash,
            "action_type": action_type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "subject_ids": subject_ids,
            "correlation_id": correlation_id,
            "prior_state": prior_state,
            "new_state": new_state,
            "safe_metadata": safe_metadata or {},
        }
        event_hash = self._event_hash(payload)
        event = AuditEvent(
            id=uuid.uuid4(),
            environment=environment,
            created_at=datetime.now(UTC),
            sequence_number=sequence,
            previous_hash=previous_hash,
            event_hash=event_hash,
            action_type=action_type,
            actor_type=actor_type,
            actor_id=actor_id,
            subject_ids=subject_ids,
            correlation_id=correlation_id,
            prior_state=prior_state,
            new_state=new_state,
            safe_metadata=safe_metadata or {},
        )
        self._session.add(event)
        return event

    async def verify_chain(self, environment: str) -> bool:
        events = (
            await self._session.scalars(
                select(AuditEvent)
                .where(AuditEvent.environment == environment)
                .order_by(AuditEvent.sequence_number)
            )
        ).all()
        previous: str | None = None
        for expected, event in enumerate(events, start=1):
            if event.sequence_number != expected or event.previous_hash != previous:
                return False
            payload = {
                "sequence": event.sequence_number,
                "previous_hash": event.previous_hash,
                "action_type": event.action_type,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "subject_ids": event.subject_ids,
                "correlation_id": event.correlation_id,
                "prior_state": event.prior_state,
                "new_state": event.new_state,
                "safe_metadata": event.safe_metadata,
            }
            if self._event_hash(payload) != event.event_hash:
                return False
            previous = event.event_hash
        return True
