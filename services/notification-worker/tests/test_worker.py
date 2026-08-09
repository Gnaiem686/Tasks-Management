from __future__ import annotations

import json

import pytest
from notification_worker.email import EmailMessage, SesEmailAdapter
from notification_worker.sqs import SqsPublisher
from notification_worker.worker import NotificationWorker, QueueMessage


class SqsClient:
    def __init__(self) -> None:
        self.calls = 0

    def send_message(self, **kwargs: object) -> dict[str, str]:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("secret endpoint")
        return {"MessageId": "safe-message-id"}


class SesClient:
    def __init__(self) -> None:
        self.destinations: list[str] = []

    def send_email(self, **kwargs: object) -> dict[str, str]:
        destination = kwargs["Destination"]
        assert isinstance(destination, dict)
        addresses = destination["ToAddresses"]
        assert isinstance(addresses, list)
        self.destinations.extend(str(address) for address in addresses)
        assert "api_key" not in str(kwargs).lower()
        return {"MessageId": "ses-id"}


class DeliveryStore:
    def __init__(self) -> None:
        self.claimed: set[str] = set()
        self.states: list[str] = []

    async def claim(self, consumer_key: str, environment: str) -> bool:
        key = f"{environment}:{consumer_key}"
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    async def mark(self, consumer_key: str, state: str, error: str | None) -> None:
        assert "secret" not in (error or "").lower()
        self.states.append(state)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sqs_publish_uses_bounded_retry_and_environment_attributes() -> None:
    client = SqsClient()
    publisher = SqsPublisher(client=client, queue_url="queue", max_attempts=2)
    message_id = await publisher.publish(
        consumer_key="alert:1", environment="dev", payload={"alert_id": "1"}
    )
    assert message_id == "safe-message-id"
    assert client.calls == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duplicate_delivery_sends_one_minimal_email() -> None:
    store = DeliveryStore()
    ses = SesClient()
    worker = NotificationWorker(
        environment="dev",
        store=store,
        email=SesEmailAdapter(client=ses, source="alerts@example.test"),
        manager_email="manager@example.test",
        application_url="https://app.example.test",
    )
    message = QueueMessage(
        message_id="m1",
        consumer_key="alert:1",
        environment="dev",
        payload={"alert_id": "1", "severity": "critical", "correlation_id": "corr-1"},
    )
    assert await worker.handle(message)
    assert await worker.handle(message)
    assert ses.destinations == ["manager@example.test"]
    assert store.states == ["sent"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cross_environment_message_is_rejected_before_email() -> None:
    store = DeliveryStore()
    ses = SesClient()
    worker = NotificationWorker(
        environment="prod",
        store=store,
        email=SesEmailAdapter(client=ses, source="alerts@example.test"),
        manager_email="manager@example.test",
        application_url="https://app.example.test",
    )
    with pytest.raises(ValueError, match="environment"):
        await worker.handle(
            QueueMessage(
                message_id="m1", consumer_key="alert:1", environment="dev", payload={}
            )
        )
    assert not ses.destinations


@pytest.mark.unit
def test_email_message_contains_link_not_workforce_payload() -> None:
    message = EmailMessage.for_alert(
        recipient="manager@example.test",
        severity="high",
        alert_id="a1",
        application_url="https://app.example.test",
        correlation_id="corr-1",
    )
    assert "https://app.example.test/alerts/a1" in message.body
    assert "employee" not in message.body.lower()
    json.dumps(message.__dict__)
