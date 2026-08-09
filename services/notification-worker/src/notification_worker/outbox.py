from __future__ import annotations

from datetime import UTC, datetime

from workforce_persistence.models import OutboxEvent
from workforce_persistence.outbox_repository import OutboxRepository

from notification_worker.sqs import SqsPublisher


class OutboxPublisher:
    def __init__(
        self, *, repository: OutboxRepository, publisher: SqsPublisher
    ) -> None:
        self._repository = repository
        self._publisher = publisher

    async def publish_event(self, event: OutboxEvent) -> str:
        event_id = event.id
        try:
            message_id = await self._publisher.publish(
                consumer_key=event.consumer_key,
                environment=event.environment,
                payload=event.payload,
            )
        except Exception as exc:
            await self._repository.record_attempt(event_id, error=type(exc).__name__)
            raise
        await self._repository.record_attempt(event_id, error=None)
        await self._repository.mark_published(event_id, published_at=datetime.now(UTC))
        return message_id
