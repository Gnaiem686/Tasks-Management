from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from workforce_risk.alerts.rules import alert_dedup_key, route_risk, should_notify
from workforce_risk.alerts.state import AlertState, validate_transition
from workforce_risk.models import RiskLevel

from workforce_persistence.models import Alert, AlertOccurrence
from workforce_persistence.outbox_repository import OutboxRepository
from workforce_persistence.repositories import AuditRepository


@dataclass(frozen=True)
class AlertRecordResult:
    alert_id: uuid.UUID
    occurrence_created: bool
    notification_created: bool
    version: int


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_risk(
        self,
        *,
        environment: str,
        subject_id: str,
        risk_type: str,
        scoring_window: str,
        risk_result_id: uuid.UUID,
        level: RiskLevel,
        evidence_fingerprint: str,
        correlation_id: str,
        now: datetime,
        cooldown: timedelta = timedelta(hours=4),
        important_new_evidence: bool = False,
    ) -> AlertRecordResult | None:
        routing = route_risk(level)
        if not routing.create_inbox_alert:
            return None
        dedup = alert_dedup_key(subject_id, risk_type, scoring_window)
        alert = await self._session.scalar(
            select(Alert)
            .where(Alert.environment == environment, Alert.dedup_key == dedup)
            .with_for_update()
        )
        previous_level: RiskLevel | None = None
        occurrence_created = False
        if alert is None:
            alert = Alert(
                id=uuid.uuid4(),
                environment=environment,
                created_at=now,
                subject_id=subject_id,
                risk_type=risk_type,
                scoring_window=scoring_window,
                dedup_key=dedup,
                state=AlertState.NEW.value,
                severity=level.value,
                evidence_fingerprint=evidence_fingerprint,
                version=1,
            )
            self._session.add(alert)
            await self._session.flush()
        else:
            previous_level = RiskLevel(alert.severity)
            if (
                alert.evidence_fingerprint == evidence_fingerprint
                and previous_level is level
            ):
                return AlertRecordResult(alert.id, False, False, alert.version)
            if alert.state in {AlertState.RESOLVED.value, AlertState.DISMISSED.value}:
                alert.state = AlertState.NEW.value
            alert.severity = level.value
            alert.evidence_fingerprint = evidence_fingerprint
            alert.version += 1
        count = await self._session.scalar(
            select(func.count())
            .select_from(AlertOccurrence)
            .where(AlertOccurrence.alert_id == alert.id)
        )
        self._session.add(
            AlertOccurrence(
                id=uuid.uuid4(),
                environment=environment,
                created_at=now,
                alert_id=alert.id,
                risk_result_id=risk_result_id,
                sequence_number=int(count or 0) + 1,
                severity=level.value,
                evidence_fingerprint=evidence_fingerprint,
            )
        )
        occurrence_created = True
        notify = should_notify(
            previous_level=previous_level,
            current_level=level,
            last_notified_at=alert.last_notified_at,
            now=now,
            cooldown=cooldown,
            important_new_evidence=important_new_evidence,
        )
        if notify:
            await OutboxRepository(self._session).append(
                environment=environment,
                consumer_key=f"alert:{alert.id}:v{alert.version}",
                event_type="risk_alert.notification_requested",
                payload={
                    "alert_id": str(alert.id),
                    "severity": level.value,
                    "correlation_id": correlation_id,
                },
                created_at=now,
            )
            alert.last_notified_at = now
        return AlertRecordResult(alert.id, occurrence_created, notify, alert.version)

    async def transition(
        self,
        *,
        alert_id: uuid.UUID,
        expected_version: int,
        target: AlertState,
        actor_id: str,
        correlation_id: str,
        dismissal_reason: str | None = None,
    ) -> bool:
        alert = await self._session.get(Alert, alert_id)
        if alert is None or alert.version != expected_version:
            return False
        current = AlertState(alert.state)
        validate_transition(current, target, dismissal_reason=dismissal_reason)
        result = await self._session.execute(
            update(Alert)
            .where(Alert.id == alert_id, Alert.version == expected_version)
            .values(state=target.value, version=Alert.version + 1)
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            return False
        await AuditRepository(self._session).append(
            environment=alert.environment,
            action_type=f"alert.{target.value}",
            actor_type="manager",
            actor_id=actor_id,
            subject_ids=[str(alert_id), alert.subject_id],
            correlation_id=correlation_id,
            prior_state={"state": current.value, "version": expected_version},
            new_state={"state": target.value, "version": expected_version + 1},
            safe_metadata={"dismissal_reason": dismissal_reason},
        )
        return True
