from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApplicationRole(StrEnum):
    VIEWER = "viewer"
    MANAGER = "manager"
    ADMINISTRATOR = "administrator"


class AuthenticatedPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: str
    display_label: str
    role: ApplicationRole
    environment: Literal["dev", "prod", "test"]
    project_scopes: tuple[str, ...]


class InternalAuthorizationError(PermissionError):
    pass


class VerifiedInternalContext(AuthenticatedPrincipal):
    correlation_id: str
    expires_at: datetime


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class InternalContextSigner:
    def __init__(self, secret: bytes, *, lifetime: timedelta) -> None:
        if len(secret) < 32:
            raise ValueError("internal context secret must contain at least 32 bytes")
        if lifetime <= timedelta(0):
            raise ValueError("internal context lifetime must be positive")
        self._secret = secret
        self._lifetime = lifetime

    def sign(
        self,
        principal: AuthenticatedPrincipal,
        *,
        correlation_id: str,
        now: datetime,
    ) -> str:
        payload = {
            **principal.model_dump(mode="json"),
            "expires_at": int((now + self._lifetime).timestamp()),
            "correlation_id": correlation_id,
        }
        encoded = _encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        signature = _encode(
            hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def verify(
        self,
        token: str | None,
        *,
        expected_environment: Literal["dev", "prod", "test"],
        required_project: str,
        required_roles: set[ApplicationRole],
        now: datetime,
    ) -> VerifiedInternalContext:
        if not token or token.count(".") != 1:
            raise InternalAuthorizationError("missing or malformed internal context")
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _encode(
            hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise InternalAuthorizationError("invalid internal context signature")
        try:
            payload: dict[str, Any] = json.loads(_decode(encoded))
            context = VerifiedInternalContext.model_validate(
                {
                    **payload,
                    "expires_at": datetime.fromtimestamp(payload["expires_at"], UTC),
                }
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InternalAuthorizationError(
                "malformed internal context claims"
            ) from exc
        if context.expires_at <= now:
            raise InternalAuthorizationError("internal context is expired")
        if context.environment != expected_environment:
            raise InternalAuthorizationError("internal context environment mismatch")
        if required_project not in context.project_scopes:
            raise InternalAuthorizationError("internal context project mismatch")
        if context.role not in required_roles:
            raise InternalAuthorizationError("internal context role mismatch")
        return context
