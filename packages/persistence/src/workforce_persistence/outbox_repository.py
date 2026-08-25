from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from workforce_persistence.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        environment: str,
        consumer_key: str,
        event_type: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> OutboxEvent:
        existing = await self._session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.environment == environment,
                OutboxEvent.consumer_key == consumer_key,
            )
        )
        if existing is not None:
            return existing
        event = OutboxEvent(
            id=uuid.uuid4(),
            environment=environment,
            created_at=created_at,
            consumer_key=consumer_key,
            event_type=event_type,
            payload=payload,
            delivery_attempts=0,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def record_attempt(self, event_id: uuid.UUID, *, error: str | None) -> None:
        await self._session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                delivery_attempts=OutboxEvent.delivery_attempts + 1,
                last_error=None if error is None else error[:500],
            )
        )

    async def mark_published(
        self, event_id: uuid.UUID, *, published_at: datetime
    ) -> None:
        await self._session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(published_at=published_at, last_error=None)
        )
