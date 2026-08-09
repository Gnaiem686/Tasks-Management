from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from workforce_persistence.models import ReportMetadata


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        *,
        environment: str,
        report_type: str,
        idempotency_key: str,
        created_at: datetime,
    ) -> ReportMetadata:
        existing = await self._session.scalar(
            select(ReportMetadata).where(
                ReportMetadata.environment == environment,
                ReportMetadata.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        record = ReportMetadata(
            id=uuid.uuid4(),
            environment=environment,
            created_at=created_at,
            report_type=report_type,
            status="pending",
            idempotency_key=idempotency_key,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def mark_stored(
        self,
        report_id: uuid.UUID,
        *,
        object_key: str,
        object_version: str,
        checksum: str,
    ) -> None:
        await self._session.execute(
            update(ReportMetadata)
            .where(ReportMetadata.id == report_id)
            .values(
                status="stored",
                object_key=object_key,
                object_version=object_version,
                checksum=checksum,
            )
        )

    async def mark_failed(self, report_id: uuid.UUID) -> None:
        await self._session.execute(
            update(ReportMetadata)
            .where(ReportMetadata.id == report_id)
            .values(status="failed")
        )
