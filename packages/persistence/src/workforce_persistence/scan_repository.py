from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from workforce_risk.scans.service import ScanState, ScanTicket

from workforce_persistence.database import Database
from workforce_persistence.models import ScanRun


class DatabaseScanStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def enqueue(
        self, *, environment: str, scope: str, idempotency_key: str, correlation_id: str
    ) -> ScanTicket:
        async with self._database.transaction() as session:
            existing = await session.scalar(
                select(ScanRun).where(
                    ScanRun.environment == environment,
                    ScanRun.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return ScanTicket(str(existing.id), ScanState(existing.state), True)
            record = ScanRun(
                id=uuid.uuid4(),
                environment=environment,
                created_at=datetime.now(UTC),
                scope=scope,
                state=ScanState.QUEUED.value,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
            session.add(record)
        return ScanTicket(str(record.id), ScanState.QUEUED)

    async def transition(
        self,
        scan_run_id: str,
        *,
        expected: ScanState,
        target: ScanState,
        failure_reason: str | None = None,
    ) -> bool:
        values: dict[str, object] = {
            "state": target.value,
            "failure_reason": failure_reason,
        }
        now = datetime.now(UTC)
        if target is ScanState.RUNNING:
            values["started_at"] = now
        if target in {
            ScanState.COMPLETED,
            ScanState.COMPLETED_DEGRADED,
            ScanState.FAILED,
            ScanState.SKIPPED_DUPLICATE,
        }:
            values["completed_at"] = now
        async with self._database.transaction() as session:
            result = await session.execute(
                update(ScanRun)
                .where(
                    ScanRun.id == uuid.UUID(scan_run_id),
                    ScanRun.state == expected.value,
                )
                .values(**values)
            )
            return cast(CursorResult[Any], result).rowcount == 1

    async def get(self, scan_run_id: str, *, environment: str) -> ScanTicket | None:
        async with self._database.transaction() as session:
            record = await session.scalar(
                select(ScanRun).where(
                    ScanRun.id == uuid.UUID(scan_run_id),
                    ScanRun.environment == environment,
                )
            )
            if record is None:
                return None
            return ScanTicket(str(record.id), ScanState(record.state))
