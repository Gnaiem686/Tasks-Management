from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from workforce_persistence.models import AuditEvent, EmployeeProfile, ScoringVersion


class ProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
