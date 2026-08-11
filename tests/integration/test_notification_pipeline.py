from __future__ import annotations

import os
import uuid

import pytest
from notification_worker.delivery_store import DatabaseDeliveryStore
from notification_worker.email import SesEmailAdapter
from notification_worker.worker import NotificationWorker, QueueMessage
from sqlalchemy import select
from workforce_persistence.database import Database
from workforce_persistence.models import NotificationDelivery

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)


class Ses:
    def __init__(self) -> None:
        self.calls = 0

    def send_email(self, **kwargs: object) -> dict[str, str]:
        self.calls += 1
        return {"MessageId": "ses-local"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_delivery_store_deduplicates_queue_redelivery() -> None:
    database = Database(DATABASE_URL)
    ses = Ses()
    consumer_key = f"integration:{uuid.uuid4()}"
    worker = NotificationWorker(
        environment="test",
        store=DatabaseDeliveryStore(database),
        email=SesEmailAdapter(client=ses, source="alerts@example.test"),
        manager_email="manager@example.test",
        application_url="https://app.example.test",
    )
    message = QueueMessage(
        message_id="message-1",
        consumer_key=consumer_key,
        environment="test",
        payload={
            "alert_id": "alert-1",
            "severity": "high",
            "correlation_id": "corr-pipeline",
        },
    )
    try:
        assert await worker.handle(message)
        assert await worker.handle(message)
        assert ses.calls == 1
        async with database.transaction() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.consumer_key == consumer_key
                )
            )
            assert delivery is not None
            assert delivery.state == "sent"
            assert delivery.attempts == 1
    finally:
        await database.close()
