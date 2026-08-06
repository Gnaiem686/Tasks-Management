from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from workforce_persistence.database import Database
from workforce_persistence.models import ApiKeyPrincipal

from agent_api.auth.api_keys import (
    ApiKeyAuthenticationError,
    ApiKeyRecord,
    ApiKeyService,
)
from agent_api.auth.principal import AuthenticatedPrincipal
from agent_api.auth.roles import ApplicationRole
from agent_api.clients.workforce_mcp import StreamableHttpProfileClient

router = APIRouter(prefix="/api/v1")


class ProfileAdministrationClient(Protocol):
    async def update_capacity(
        self,
        *,
        employee_id: str,
        project_key: str,
        expected_version: int,
        weekly_capacity_hours: float,
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]: ...


class CapacityChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekly_capacity_hours: float = Field(gt=0, le=168)


async def get_administrator(
    project_key: Annotated[str, Query(min_length=1)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal:
    raw_environment = os.getenv("APP_ENVIRONMENT", "dev")
    environment = cast(Literal["dev", "prod", "test"], raw_environment)
    database_url = os.getenv("DATABASE_URL")
    pepper = os.getenv("API_KEY_HMAC_PEPPER")
    if not database_url or not pepper:
        raise HTTPException(status_code=503, detail="authentication unavailable")
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            rows = (await session.scalars(select(ApiKeyPrincipal))).all()
            records = tuple(
                ApiKeyRecord(
                    actor_id=row.actor_id,
                    display_label=row.display_label,
                    key_digest=row.key_digest,
                    role=ApplicationRole(row.role),
                    environment=cast(Literal["dev", "prod", "test"], row.environment),
                    project_scopes=tuple(row.project_scopes),
                    created_at=row.created_at,
                    expires_at=row.expires_at,
                    revoked_at=row.revoked_at,
                )
                for row in rows
            )
        return ApiKeyService(pepper.encode()).authenticate(
            authorization,
            records=records,
            environment=environment,
            project_key=project_key,
            allowed_roles={ApplicationRole.ADMINISTRATOR},
            now=datetime.now(UTC),
        )
    except ApiKeyAuthenticationError as exc:
        status = 403 if "role" in str(exc) or "scope" in str(exc) else 401
        raise HTTPException(status_code=status, detail="not authorized") from exc
    finally:
        await database.close()


def get_profile_client() -> ProfileAdministrationClient:
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    if not secret:
        raise RuntimeError("INTERNAL_AUTH_SECRET is required")
    return StreamableHttpProfileClient(
        url=os.getenv("WORKFORCE_MCP_URL", "http://127.0.0.1:8001/mcp"),
        secret=secret.encode(),
    )


@router.patch("/profiles/{employee_id}/capacity")
async def update_profile_capacity(
    employee_id: str,
    change: CapacityChange,
    response: Response,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_administrator)],
    client: Annotated[ProfileAdministrationClient, Depends(get_profile_client)],
    if_match: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match is required")
    try:
        expected_version = int(if_match.strip('"'))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid If-Match") from exc
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    result = await client.update_capacity(
        employee_id=employee_id,
        project_key=project_key,
        expected_version=expected_version,
        weekly_capacity_hours=change.weekly_capacity_hours,
        principal=principal,
        correlation_id=correlation_id,
    )
    response.headers["ETag"] = f'"{result["version"]}"'
    response.headers["X-Correlation-ID"] = correlation_id
    return result
