from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from notification_worker.email import EmailMessage, SesEmailAdapter


@dataclass(frozen=True)
class QueueMessage:
    message_id: str
    consumer_key: str
    environment: Literal["dev", "prod", "test"]
    payload: dict[str, object]


class DeliveryStore(Protocol):
    async def claim(self, consumer_key: str, environment: str) -> bool: ...
    async def mark(self, consumer_key: str, state: str, error: str | None) -> None: ...


class NotificationWorker:
    def __init__(
        self,
        *,
        environment: str,
        store: DeliveryStore,
        email: SesEmailAdapter,
        manager_email: str,
        application_url: str,
    ) -> None:
        self._environment = environment
        self._store = store
        self._email = email
        self._manager_email = manager_email
        self._application_url = application_url

    async def handle(self, message: QueueMessage) -> bool:
        if message.environment != self._environment:
            raise ValueError("notification environment mismatch")
        if not await self._store.claim(message.consumer_key, message.environment):
            return True
        try:
            payload = message.payload
            email = EmailMessage.for_alert(
                recipient=self._manager_email,
                severity=str(payload.get("severity", "risk")),
                alert_id=str(payload["alert_id"]),
                application_url=self._application_url,
                correlation_id=str(payload.get("correlation_id", "unavailable")),
            )
            await self._email.send(email)
        except Exception as exc:
            await self._store.mark(message.consumer_key, "retrying", type(exc).__name__)
            return False
        await self._store.mark(message.consumer_key, "sent", None)
        return True
