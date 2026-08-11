from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "password",
        "secret",
        "token",
        "raw_jwt",
        "prompt",
        "system_prompt",
        "credentials",
    }
)


def structured_event(
    event: str,
    *,
    correlation_id: str,
    environment: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "environment": environment,
        "correlation_id": correlation_id,
        "metadata": _redact(metadata or {}),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _redact(value: Any, key: str | None = None) -> Any:
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(item_key): _redact(item, str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
