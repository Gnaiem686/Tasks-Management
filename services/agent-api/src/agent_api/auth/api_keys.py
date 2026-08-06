from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from agent_api.auth.principal import AuthenticatedPrincipal
from agent_api.auth.roles import ApplicationRole


class ApiKeyAuthenticationError(PermissionError):
    pass


class ApiKeyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: str
    display_label: str
    key_digest: str
    role: ApplicationRole
    environment: Literal["dev", "prod", "test"]
    project_scopes: tuple[str, ...]
    created_at: AwareDatetime
    expires_at: AwareDatetime | None = None
    revoked_at: AwareDatetime | None = None


class ApiKeyService:
    def __init__(self, pepper: bytes) -> None:
        if len(pepper) < 32:
            raise ValueError("API-key HMAC pepper must contain at least 32 bytes")
        self._pepper = pepper

    def _digest(self, raw_key: str) -> str:
        return hmac.new(self._pepper, raw_key.encode(), hashlib.sha256).hexdigest()

    def generate(
        self,
        *,
        actor_id: str,
        display_label: str,
        role: ApplicationRole,
        environment: Literal["dev", "prod", "test"],
        project_scopes: tuple[str, ...],
        now: datetime,
        expires_at: datetime | None = None,
    ) -> tuple[str, ApiKeyRecord]:
        raw_key = f"wrk_{environment}_{secrets.token_urlsafe(32)}"
        return raw_key, ApiKeyRecord(
            actor_id=actor_id,
            display_label=display_label,
            key_digest=self._digest(raw_key),
            role=role,
            environment=environment,
            project_scopes=project_scopes,
            created_at=now,
            expires_at=expires_at,
        )

    def authenticate(
        self,
        authorization: str | None,
        *,
        records: tuple[ApiKeyRecord, ...],
        environment: Literal["dev", "prod", "test"],
        project_key: str,
        allowed_roles: set[ApplicationRole],
        now: datetime,
    ) -> AuthenticatedPrincipal:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiKeyAuthenticationError("missing or malformed API key")
        raw_key = authorization.removeprefix("Bearer ").strip()
        if not raw_key.startswith("wrk_") or any(
            character.isspace() for character in raw_key
        ):
            raise ApiKeyAuthenticationError("missing or malformed API key")
        digest = self._digest(raw_key)
        record = next(
            (
                candidate
                for candidate in records
                if hmac.compare_digest(candidate.key_digest, digest)
            ),
            None,
        )
        if record is None:
            raise ApiKeyAuthenticationError("unknown API key")
        if record.revoked_at is not None:
            raise ApiKeyAuthenticationError("API key is revoked")
        if record.expires_at is not None and record.expires_at <= now:
            raise ApiKeyAuthenticationError("API key is expired")
        if record.environment != environment:
            raise ApiKeyAuthenticationError("API key environment mismatch")
        if project_key not in record.project_scopes:
            raise ApiKeyAuthenticationError("API key project scope mismatch")
        if record.role not in allowed_roles:
            raise ApiKeyAuthenticationError("API key role is not authorized")
        return AuthenticatedPrincipal(
            actor_id=record.actor_id,
            display_label=record.display_label,
            role=record.role,
            environment=record.environment,
            project_scopes=record.project_scopes,
        )
