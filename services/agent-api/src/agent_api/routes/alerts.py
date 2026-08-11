from __future__ import annotations

import os
import uuid
from typing import Annotated, Any, Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc, desc, func, select
from workforce_contracts.auth import ApplicationRole, AuthenticatedPrincipal
from workforce_persistence.alert_repository import AlertRepository
from workforce_persistence.database import Database
from workforce_persistence.models import Alert, AlertOccurrence
from workforce_risk.alerts.state import AlertState

from agent_api.routes.investigations import get_investigator
from agent_api.security.environment import enforce_project_scope

router = APIRouter(prefix="/api/v1")


class AlertStore(Protocol):
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]: ...
    async def transition(self, **kwargs: Any) -> dict[str, Any] | None: ...


class AlertTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["acknowledged", "resolved", "dismissed"]
    dismissal_reason: str | None = None


class DatabaseAlertStore:
    def __init__(self, url: str) -> None:
        self._database = Database(url)

    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        environment, page, page_size = (
            kwargs["environment"],
            kwargs["page"],
            kwargs["page_size"],
        )
        order = (
            desc(Alert.created_at)
            if kwargs["sort"] == "-created_at"
            else asc(Alert.created_at)
        )
        filters = [Alert.environment == environment]
        if kwargs.get("state"):
            filters.append(Alert.state == kwargs["state"])
        if kwargs.get("severity"):
            filters.append(Alert.severity == kwargs["severity"])
        async with self._database.transaction() as session:
            total = int(
                await session.scalar(
                    select(func.count()).select_from(Alert).where(*filters)
                )
                or 0
            )
            records = (
                await session.scalars(
                    select(Alert)
                    .where(*filters)
                    .order_by(order, Alert.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            items: list[dict[str, Any]] = []
            for record in records:
                recurrence = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(AlertOccurrence)
                        .where(AlertOccurrence.alert_id == record.id)
                    )
                    or 0
                )
                items.append(
                    {
                        "id": str(record.id),
                        "subject_id": record.subject_id,
                        "risk_type": record.risk_type,
                        "state": record.state,
                        "severity": record.severity,
                        "version": record.version,
                        "created_at": record.created_at.isoformat(),
                        "recurrence_count": recurrence,
                    }
                )
        await self._database.close()
        return items, total

    async def transition(self, **kwargs: Any) -> dict[str, Any] | None:
        async with self._database.transaction() as session:
            changed = await AlertRepository(session).transition(
                alert_id=uuid.UUID(kwargs["alert_id"]),
                expected_version=kwargs["expected_version"],
                target=AlertState(kwargs["state"]),
                actor_id=kwargs["actor_id"],
                correlation_id=kwargs["correlation_id"],
                dismissal_reason=kwargs.get("dismissal_reason"),
            )
            if not changed:
                return None
            record = await session.get(Alert, uuid.UUID(kwargs["alert_id"]))
            assert record is not None
            result = {
                "id": str(record.id),
                "state": record.state,
                "severity": record.severity,
                "version": record.version,
            }
        await self._database.close()
        return result


def get_alert_store() -> AlertStore:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(status_code=503, detail="alert store unavailable")
    return DatabaseAlertStore(url)


@router.get("/alerts")
async def list_alerts(
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_investigator)],
    store: Annotated[AlertStore, Depends(get_alert_store)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["created_at", "-created_at"] = "-created_at",
    state: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    enforce_project_scope(project_key, principal)
    items, total = await store.list(
        environment=principal.environment,
        page=page,
        page_size=page_size,
        sort=sort,
        state=state,
        severity=severity,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.patch("/alerts/{alert_id}")
async def transition_alert(
    alert_id: str,
    change: AlertTransition,
    response: Response,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_investigator)],
    store: Annotated[AlertStore, Depends(get_alert_store)],
    if_match: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    enforce_project_scope(project_key, principal)
    if principal.role not in {ApplicationRole.MANAGER, ApplicationRole.ADMINISTRATOR}:
        raise HTTPException(status_code=403, detail="alert changes require manager")
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match is required")
    try:
        version = int(if_match.strip('"'))
        uuid.UUID(alert_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="invalid alert version or ID"
        ) from exc
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    result = await store.transition(
        alert_id=alert_id,
        expected_version=version,
        state=change.state,
        dismissal_reason=change.dismissal_reason,
        actor_id=principal.actor_id,
        correlation_id=correlation_id,
    )
    if result is None:
        raise HTTPException(status_code=409, detail="alert version conflict")
    response.headers["ETag"] = f'"{result["version"]}"'
    response.headers["X-Correlation-ID"] = correlation_id
    return result
