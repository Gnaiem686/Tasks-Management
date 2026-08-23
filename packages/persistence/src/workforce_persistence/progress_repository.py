from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workforce_persistence.models import (
    TaskCurrentState,
    TaskProgressEvent,
    TaskProgressSnapshot,
    WorkWeek,
)


class TaskProgressObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,19}$")
    issue_key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,19}-[1-9][0-9]*$")
    assignee_id: str | None = None
    captured_at: AwareDatetime
    jira_updated_at: AwareDatetime
    status: str = Field(min_length=1, max_length=128)
    original_estimate_hours: float | None = Field(default=None, ge=0)
    remaining_estimate_hours: float | None = Field(default=None, ge=0)
    time_spent_hours: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    priority: str | None = None
    blocked: bool
    blocker_issue_keys: tuple[str, ...] = ()

    def canonical_state(self) -> dict[str, Any]:
        return {
            "project_key": self.project_key,
            "issue_key": self.issue_key,
            "assignee_id": self.assignee_id,
            "status": self.status,
            "original_estimate_hours": self.original_estimate_hours,
            "remaining_estimate_hours": self.remaining_estimate_hours,
            "time_spent_hours": self.time_spent_hours,
            "due_date": None if self.due_date is None else self.due_date.isoformat(),
            "priority": self.priority,
            "blocked": self.blocked,
            "blocker_issue_keys": sorted(set(self.blocker_issue_keys)),
        }

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.canonical_state(), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()


class DerivedProgressEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    event_type: str
    old_value: Any | None = None
    new_value: Any | None = None
    structured_progress: bool = False


class ProgressPersistenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed: int
    snapshots_created: int
    events_created: int


def derive_progress_events(
    previous: TaskProgressObservation, current: TaskProgressObservation
) -> tuple[DerivedProgressEvent, ...]:
    events: list[DerivedProgressEvent] = []

    def json_value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    def changed(
        event_type: str,
        old: Any,
        new: Any,
        *,
        progress: bool = False,
    ) -> None:
        if old != new:
            events.append(
                DerivedProgressEvent(
                    event_type=event_type,
                    old_value=json_value(old),
                    new_value=json_value(new),
                    structured_progress=progress,
                )
            )

    changed(
        "remaining_estimate_changed",
        previous.remaining_estimate_hours,
        current.remaining_estimate_hours,
        progress=(
            previous.remaining_estimate_hours is not None
            and current.remaining_estimate_hours is not None
            and current.remaining_estimate_hours < previous.remaining_estimate_hours
        ),
    )
    if previous.time_spent_hours != current.time_spent_hours:
        increased = (
            previous.time_spent_hours is not None
            and current.time_spent_hours is not None
            and current.time_spent_hours > previous.time_spent_hours
        ) or (
            previous.time_spent_hours is None and current.time_spent_hours is not None
        )
        events.append(
            DerivedProgressEvent(
                event_type="work_logged" if increased else "time_spent_corrected",
                old_value=previous.time_spent_hours,
                new_value=current.time_spent_hours,
                structured_progress=increased,
            )
        )
    changed(
        "status_changed",
        previous.status,
        current.status,
        progress=True,
    )
    changed(
        "original_estimate_changed",
        previous.original_estimate_hours,
        current.original_estimate_hours,
    )
    changed("due_date_changed", previous.due_date, current.due_date)
    changed("priority_changed", previous.priority, current.priority)
    changed("assignee_changed", previous.assignee_id, current.assignee_id)

    previous_blockers = set(previous.blocker_issue_keys)
    current_blockers = set(current.blocker_issue_keys)
    if not previous.blocked and current.blocked or current_blockers - previous_blockers:
        events.append(
            DerivedProgressEvent(
                event_type="blocker_added",
                old_value=sorted(previous_blockers),
                new_value=sorted(current_blockers),
            )
        )
    if previous.blocked and not current.blocked or previous_blockers - current_blockers:
        events.append(
            DerivedProgressEvent(
                event_type="blocker_removed",
                old_value=sorted(previous_blockers),
                new_value=sorted(current_blockers),
            )
        )
    if previous.status.casefold() not in {"done", "closed", "resolved"} and (
        current.status.casefold() in {"done", "closed", "resolved"}
    ):
        events.append(
            DerivedProgressEvent(
                event_type="task_completed",
                old_value=previous.status,
                new_value=current.status,
                structured_progress=True,
            )
        )
    return tuple(events)


class TaskProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_history_records(
        self,
        *,
        environment: str,
        project_key: str,
        limit: int = 200,
    ) -> tuple[dict[str, Any], ...]:
        """Return bounded, JSON-safe task changes and baseline snapshots."""

        bounded_limit = max(1, min(limit, 500))
        events = (
            await self._session.scalars(
                select(TaskProgressEvent)
                .where(
                    TaskProgressEvent.environment == environment,
                    TaskProgressEvent.project_key == project_key,
                )
                .order_by(TaskProgressEvent.occurred_at.desc())
                .limit(bounded_limit)
            )
        ).all()
        remaining = max(0, bounded_limit - len(events))
        snapshots = (
            (
                await self._session.scalars(
                    select(TaskProgressSnapshot)
                    .where(
                        TaskProgressSnapshot.environment == environment,
                        TaskProgressSnapshot.project_key == project_key,
                    )
                    .order_by(TaskProgressSnapshot.captured_at.desc())
                    .limit(remaining)
                )
            ).all()
            if remaining
            else []
        )
        records: list[dict[str, Any]] = [
            {
                "record_type": "progress_event",
                "issue_key": row.issue_key,
                "employee_reference": row.employee_id,
                "event_type": row.event_type,
                "occurred_at": row.occurred_at.isoformat(),
                "old_value": row.old_value,
                "new_value": row.new_value,
                "source": row.source,
            }
            for row in events
        ]
        records.extend(
            {
                "record_type": "task_snapshot",
                "issue_key": row.issue_key,
                "employee_reference": row.assignee_id,
                "captured_at": row.captured_at.isoformat(),
                "jira_updated_at": row.jira_updated_at.isoformat(),
                "status": row.status,
                "original_estimate_hours": row.original_estimate_hours,
                "remaining_estimate_hours": row.remaining_estimate_hours,
                "time_spent_hours": row.time_spent_hours,
                "due_date": None if row.due_date is None else row.due_date.isoformat(),
                "priority": row.priority,
                "blocked": row.blocked,
                "blocker_issue_keys": row.blocker_issue_keys,
                "source": row.source,
            }
            for row in snapshots
        )
        return tuple(records)

    async def record_observations(
        self,
        *,
        environment: str,
        observations: tuple[TaskProgressObservation, ...],
        timezone_name: str = "Asia/Jerusalem",
    ) -> ProgressPersistenceResult:
        snapshots_created = 0
        events_created = 0
        for observation in observations:
            work_week = await self._work_week(
                environment=environment,
                project_key=observation.project_key,
                captured_at=observation.captured_at,
                timezone_name=timezone_name,
            )
            current = await self._session.scalar(
                select(TaskCurrentState).where(
                    TaskCurrentState.environment == environment,
                    TaskCurrentState.project_key == observation.project_key,
                    TaskCurrentState.issue_key == observation.issue_key,
                )
            )
            fingerprint = observation.fingerprint()
            previous = (
                None
                if current is None
                else TaskProgressObservation.model_validate(current.state)
            )
            events = (
                ()
                if previous is None
                else derive_progress_events(previous, observation)
            )
            week_changed = current is not None and current.work_week_id != work_week.id
            state_changed = (
                current is None or current.evidence_fingerprint != fingerprint
            )
            if state_changed or week_changed:
                self._session.add(
                    TaskProgressSnapshot(
                        id=uuid.uuid4(),
                        environment=environment,
                        created_at=observation.captured_at,
                        work_week_id=work_week.id,
                        project_key=observation.project_key,
                        issue_key=observation.issue_key,
                        assignee_id=observation.assignee_id,
                        captured_at=observation.captured_at,
                        jira_updated_at=observation.jira_updated_at,
                        status=observation.status,
                        original_estimate_hours=observation.original_estimate_hours,
                        remaining_estimate_hours=observation.remaining_estimate_hours,
                        time_spent_hours=observation.time_spent_hours,
                        due_date=observation.due_date,
                        priority=observation.priority,
                        blocked=observation.blocked,
                        blocker_issue_keys=list(observation.blocker_issue_keys),
                        source="jira",
                        evidence_fingerprint=fingerprint,
                    )
                )
                snapshots_created += 1
            last_progress = (
                None if current is None else current.last_structured_progress_at
            )
            if current is None:
                last_progress = observation.jira_updated_at
            if any(event.structured_progress for event in events):
                last_progress = observation.jira_updated_at
            if current is None:
                current = TaskCurrentState(
                    id=uuid.uuid4(),
                    environment=environment,
                    created_at=observation.captured_at,
                    project_key=observation.project_key,
                    issue_key=observation.issue_key,
                    work_week_id=work_week.id,
                    evidence_fingerprint=fingerprint,
                    last_observed_at=observation.captured_at,
                    jira_updated_at=observation.jira_updated_at,
                    last_structured_progress_at=last_progress,
                    state=observation.model_dump(mode="json"),
                )
                self._session.add(current)
            else:
                current.work_week_id = work_week.id
                current.evidence_fingerprint = fingerprint
                current.last_observed_at = observation.captured_at
                current.jira_updated_at = observation.jira_updated_at
                current.last_structured_progress_at = last_progress
                current.state = observation.model_dump(mode="json")
            for event in events:
                material = {
                    "environment": environment,
                    "issue_key": observation.issue_key,
                    "event_type": event.event_type,
                    "occurred_at": observation.jira_updated_at.isoformat(),
                    "old": event.old_value,
                    "new": event.new_value,
                }
                event_fingerprint = hashlib.sha256(
                    json.dumps(material, sort_keys=True, default=str).encode()
                ).hexdigest()
                self._session.add(
                    TaskProgressEvent(
                        id=uuid.uuid4(),
                        environment=environment,
                        created_at=observation.captured_at,
                        work_week_id=work_week.id,
                        project_key=observation.project_key,
                        issue_key=observation.issue_key,
                        employee_id=observation.assignee_id,
                        event_type=event.event_type,
                        occurred_at=observation.jira_updated_at,
                        old_value=event.old_value,
                        new_value=event.new_value,
                        source="jira",
                        event_fingerprint=event_fingerprint,
                    )
                )
                events_created += 1
        await self._session.flush()
        return ProgressPersistenceResult(
            observed=len(observations),
            snapshots_created=snapshots_created,
            events_created=events_created,
        )

    async def _work_week(
        self,
        *,
        environment: str,
        project_key: str,
        captured_at: datetime,
        timezone_name: str,
    ) -> WorkWeek:
        local_date = captured_at.astimezone(ZoneInfo(timezone_name)).date()
        week_start = local_date - timedelta(days=local_date.weekday())
        existing = await self._session.scalar(
            select(WorkWeek).where(
                WorkWeek.environment == environment,
                WorkWeek.project_key == project_key,
                WorkWeek.week_start == week_start,
            )
        )
        if existing is not None:
            return existing
        record = WorkWeek(
            id=uuid.uuid4(),
            environment=environment,
            created_at=captured_at,
            project_key=project_key,
            week_start=week_start,
            week_end=week_start + timedelta(days=4),
        )
        self._session.add(record)
        await self._session.flush()
        return record
