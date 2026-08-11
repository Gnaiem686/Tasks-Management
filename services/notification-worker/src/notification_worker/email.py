from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol


class SesClient(Protocol):
    def send_email(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class EmailMessage:
    recipient: str
    subject: str
    body: str

    @classmethod
    def for_alert(
        cls,
        *,
        recipient: str,
        severity: str,
        alert_id: str,
        application_url: str,
        correlation_id: str,
    ) -> EmailMessage:
        return cls(
            recipient=recipient,
            subject=f"Workforce delivery risk: {severity}",
            body=(
                f"A {severity} work-delivery risk needs review.\n"
                f"Open {application_url.rstrip('/')}/alerts/{alert_id}\n"
                f"Support reference: {correlation_id}"
            ),
        )


class SesEmailAdapter:
    def __init__(self, *, client: SesClient, source: str) -> None:
        self._client = client
        self._source = source

    async def send(self, message: EmailMessage) -> str:
        response = await asyncio.to_thread(
            self._client.send_email,
            Source=self._source,
            Destination={"ToAddresses": [message.recipient]},
            Message={
                "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": message.body, "Charset": "UTF-8"}},
            },
        )
        return str(response["MessageId"])
