from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SafeAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence_number: int
    previous_hash: str | None
    action_type: str
    actor_type: str
    actor_id: str
    subject_ids: tuple[str, ...]
    correlation_id: str
    safe_metadata: dict[str, object]
    event_hash: str
