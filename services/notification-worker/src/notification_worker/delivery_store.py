from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from workforce_persistence.database import Database
from workforce_persistence.models import NotificationDelivery


class DatabaseDeliveryStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def claim(self, consumer_key: str, environment: str) -> bool:
        async with self._database.transaction() as session:
            existing = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.environment == environment,
                    NotificationDelivery.consumer_key == consumer_key,
                )
            )
            if existing is not None:
                return existing.state not in {"sending", "sent", "failed"}
            session.add(
                NotificationDelivery(
                    id=uuid.uuid4(),
                    environment=environment,
                    created_at=datetime.now(UTC),
                    consumer_key=consumer_key,
                    state="sending",
                    attempts=0,
                )
            )
        return True

    async def mark(self, consumer_key: str, state: str, error: str | None) -> None:
        safe_error = None if error is None else error[:128]
        async with self._database.transaction() as session:
            await session.execute(
                update(NotificationDelivery)
                .where(NotificationDelivery.consumer_key == consumer_key)
                .values(
                    state=state,
                    attempts=NotificationDelivery.attempts + 1,
                    last_error=safe_error,
                )
            )
