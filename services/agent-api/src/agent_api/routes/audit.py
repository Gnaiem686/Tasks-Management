from __future__ import annotations

import os
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, select
from workforce_contracts.auth import ApplicationRole, AuthenticatedPrincipal
from workforce_persistence.database import Database
from workforce_persistence.models import AuditEvent
from workforce_persistence.repositories import AuditRepository

from agent_api.routes.investigations import get_investigator
from agent_api.security.environment import enforce_project_scope

router = APIRouter(prefix="/api/v1")
FORBIDDEN_METADATA_KEYS = ("token", "secret", "password", "credential", "authorization")


class AuditStore(Protocol):
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int, bool]: ...


def safe_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: safe_metadata(item)
            for key, item in value.items()
            if not any(term in key.lower() for term in FORBIDDEN_METADATA_KEYS)
        }
    if isinstance(value, list):
        return [safe_metadata(item) for item in value]
    return value


class DatabaseAuditStore:
    def __init__(self, url: str) -> None:
        self._database = Database(url)

    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int, bool]:
        environment, page, page_size = (
            kwargs["environment"],
            kwargs["page"],
            kwargs["page_size"],
        )
        order = (
            desc(AuditEvent.sequence_number)
            if kwargs["sort"] == "-sequence"
            else asc(AuditEvent.sequence_number)
        )
        async with self._database.transaction() as session:
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.environment == environment)
                )
                or 0
            )
            rows = (
                await session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.environment == environment)
                    .order_by(order)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            chain_valid = await AuditRepository(session).verify_chain(environment)
            items = [
                {
                    "sequence_number": row.sequence_number,
                    "created_at": row.created_at.isoformat(),
                    "action_type": row.action_type,
                    "actor_type": row.actor_type,
                    "actor_id": row.actor_id,
                    "subject_ids": row.subject_ids,
                    "prior_state": safe_metadata(row.prior_state),
                    "new_state": safe_metadata(row.new_state),
                    "correlation_id": row.correlation_id,
                    "safe_metadata": safe_metadata(row.safe_metadata),
                }
                for row in rows
            ]
        await self._database.close()
        return items, total, chain_valid


def get_audit_store() -> AuditStore:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(status_code=503, detail="audit store unavailable")
    return DatabaseAuditStore(url)


@router.get("/audit")
async def list_audit(
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_investigator)],
    store: Annotated[AuditStore, Depends(get_audit_store)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: str = "-sequence",
) -> dict[str, Any]:
    enforce_project_scope(project_key, principal)
    if principal.role is not ApplicationRole.ADMINISTRATOR:
        raise HTTPException(
            status_code=403, detail="audit access requires administrator"
        )
    if sort not in {"sequence", "-sequence"}:
        raise HTTPException(status_code=422, detail="unsupported sort")
    items, total, chain_valid = await store.list(
        environment=principal.environment, page=page, page_size=page_size, sort=sort
    )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "chain_valid": chain_valid,
    }
