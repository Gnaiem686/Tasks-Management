from __future__ import annotations

import asyncio
import importlib
import os
import uuid
from typing import Annotated, Any, Protocol, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from workforce_contracts.auth import AuthenticatedPrincipal
from workforce_persistence.database import Database
from workforce_persistence.models import ReportMetadata

from agent_api.routes.investigations import get_investigator
from agent_api.security.environment import enforce_project_scope

router = APIRouter(prefix="/api/v1")


class ReportStore(Protocol):
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]: ...
    async def download_url(self, **kwargs: Any) -> str | None: ...


class DatabaseReportStore:
    def __init__(self, url: str, bucket: str, client: Any) -> None:
        self._database, self._bucket, self._client = Database(url), bucket, client

    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        environment, page, page_size = (
            kwargs["environment"],
            kwargs["page"],
            kwargs["page_size"],
        )
        async with self._database.transaction() as session:
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ReportMetadata)
                    .where(ReportMetadata.environment == environment)
                )
                or 0
            )
            rows = (
                await session.scalars(
                    select(ReportMetadata)
                    .where(ReportMetadata.environment == environment)
                    .order_by(desc(ReportMetadata.created_at), ReportMetadata.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            items = [
                {
                    "id": str(row.id),
                    "report_type": row.report_type,
                    "status": row.status,
                    "created_at": row.created_at.isoformat(),
                    "object_version": row.object_version,
                    "checksum": row.checksum,
                }
                for row in rows
            ]
        await self._database.close()
        return items, total

    async def download_url(self, **kwargs: Any) -> str | None:
        async with self._database.transaction() as session:
            record = await session.scalar(
                select(ReportMetadata).where(
                    ReportMetadata.id == uuid.UUID(kwargs["report_id"]),
                    ReportMetadata.environment == kwargs["environment"],
                    ReportMetadata.status == "stored",
                )
            )
            if record is None or not record.object_key or not record.object_version:
                return None
            if not record.object_key.startswith(f"reports/{kwargs['environment']}/"):
                raise PermissionError("report object is outside environment scope")
            params = {
                "Bucket": self._bucket,
                "Key": record.object_key,
                "VersionId": record.object_version,
            }
        await self._database.close()
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params=params,
            ExpiresIn=300,
        )


def get_report_store() -> ReportStore:
    url, bucket = os.getenv("DATABASE_URL"), os.getenv("REPORT_BUCKET")
    if not url or not bucket:
        raise HTTPException(status_code=503, detail="report store unavailable")
    boto3 = importlib.import_module("boto3")
    return DatabaseReportStore(url, bucket, cast(Any, boto3).client("s3"))


@router.get("/reports")
async def list_reports(
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_investigator)],
    store: Annotated[ReportStore, Depends(get_report_store)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    enforce_project_scope(project_key, principal)
    items, total = await store.list(
        environment=principal.environment, page=page, page_size=page_size
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/reports/{report_id}/download")
async def download_report(
    report_id: str,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_investigator)],
    store: Annotated[ReportStore, Depends(get_report_store)],
) -> dict[str, Any]:
    enforce_project_scope(project_key, principal)
    try:
        uuid.UUID(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="report not found") from exc
    url = await store.download_url(
        report_id=report_id, environment=principal.environment
    )
    if url is None:
        raise HTTPException(status_code=404, detail="report not found")
    return {"url": url, "expires_in": 300}
