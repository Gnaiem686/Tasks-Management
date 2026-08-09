from __future__ import annotations

import hashlib
import json


def event_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def verify_hash_chain(events: tuple[dict[str, object], ...]) -> bool:
    previous: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        if event.get("sequence_number") != expected_sequence:
            return False
        if event.get("previous_hash") != previous:
            return False
        supplied = event.get("event_hash")
        material = {key: value for key, value in event.items() if key != "event_hash"}
        if supplied != event_hash(material):
            return False
        previous = str(supplied)
    return True
