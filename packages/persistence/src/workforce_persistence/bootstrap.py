from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
from datetime import UTC, datetime

from sqlalchemy import select

from workforce_persistence.database import Database
from workforce_persistence.models import ApiKeyPrincipal


def build_initial_principal(
    *,
    raw_key: str,
    pepper: str,
    environment: str,
    project_key: str,
    now: datetime,
) -> ApiKeyPrincipal:
    if len(pepper.encode()) < 32:
        raise ValueError("API-key HMAC pepper must contain at least 32 bytes")
    if not raw_key.startswith(f"wrk_{environment}_"):
        raise ValueError("initial API key does not match the environment")
    digest = hmac.new(pepper.encode(), raw_key.encode(), hashlib.sha256).hexdigest()
    return ApiKeyPrincipal(
        environment=environment,
        created_at=now,
        actor_id=f"initial-{environment}-manager",
        display_label=f"Initial {environment} manager",
        key_digest=digest,
        role="manager",
        project_scopes=[project_key],
        expires_at=None,
        revoked_at=None,
    )


async def bootstrap() -> None:
    required = {
        name: os.environ.get(name)
        for name in (
            "DATABASE_URL",
            "INITIAL_API_KEY",
            "API_KEY_HMAC_PEPPER",
            "APP_ENVIRONMENT",
            "JIRA_PROJECT_KEY",
        )
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"missing bootstrap configuration: {', '.join(missing)}")
    principal = build_initial_principal(
        raw_key=str(required["INITIAL_API_KEY"]),
        pepper=str(required["API_KEY_HMAC_PEPPER"]),
        environment=str(required["APP_ENVIRONMENT"]),
        project_key=str(required["JIRA_PROJECT_KEY"]),
        now=datetime.now(UTC),
    )
    database = Database(str(required["DATABASE_URL"]))
    try:
        async with database.transaction() as session:
            existing = await session.scalar(
                select(ApiKeyPrincipal.id).where(
                    ApiKeyPrincipal.key_digest == principal.key_digest
                )
            )
            if existing is None:
                session.add(principal)
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(bootstrap())
