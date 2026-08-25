from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol


class SqsClient(Protocol):
    def send_message(self, **kwargs: Any) -> dict[str, Any]: ...


class SqsPublisher:
    def __init__(
        self, *, client: SqsClient, queue_url: str, max_attempts: int = 3
    ) -> None:
        self._client = client
        self._queue_url = queue_url
        self._max_attempts = max(1, max_attempts)

    async def publish(
        self, *, consumer_key: str, environment: str, payload: dict[str, object]
    ) -> str:
        body = json.dumps(
            {
                "consumer_key": consumer_key,
                "environment": environment,
                "payload": payload,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        for attempt in range(self._max_attempts):
            try:
                response = await asyncio.to_thread(
                    self._client.send_message,
                    QueueUrl=self._queue_url,
                    MessageBody=body,
                    MessageAttributes={
                        "environment": {
                            "DataType": "String",
                            "StringValue": environment,
                        }
                    },
                )
                return str(response["MessageId"])
            except (TimeoutError, ConnectionError, OSError):
                if attempt + 1 == self._max_attempts:
                    raise
                await asyncio.sleep(min(0.05 * 2**attempt, 0.2))
        raise RuntimeError("unreachable")
