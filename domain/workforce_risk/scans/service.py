from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ScanState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_DEGRADED = "completed_degraded"
    FAILED = "failed"
    SKIPPED_DUPLICATE = "skipped_duplicate"


@dataclass(frozen=True)
class ScanTicket:
    scan_run_id: str
    state: ScanState
    duplicate: bool = False


@dataclass(frozen=True)
class PipelineResult:
    degraded: bool
    risk_result_ids: tuple[str, ...]
    alert_ids: tuple[str, ...]
    report_id: str | None


class ScanStore(Protocol):
    async def enqueue(
        self, *, environment: str, scope: str, idempotency_key: str, correlation_id: str
    ) -> ScanTicket: ...
    async def transition(
        self,
        scan_run_id: str,
        *,
        expected: ScanState,
        target: ScanState,
        failure_reason: str | None = None,
    ) -> bool: ...
    async def get(self, scan_run_id: str, *, environment: str) -> ScanTicket | None: ...


class ScanPipeline(Protocol):
    async def run(self, *, scope: str, correlation_id: str) -> PipelineResult: ...


def scan_window_key(environment: str, scope: str, window: str) -> str:
    return hashlib.sha256(f"{environment}:{scope}:{window}".encode()).hexdigest()


class ScanService:
    def __init__(
        self, *, environment: str, store: ScanStore, pipeline: ScanPipeline
    ) -> None:
        self._environment = environment
        self._store = store
        self._pipeline = pipeline

    async def request(
        self, *, scope: str, window: str, correlation_id: str
    ) -> ScanTicket:
        return await self._store.enqueue(
            environment=self._environment,
            scope=scope,
            idempotency_key=scan_window_key(self._environment, scope, window),
            correlation_id=correlation_id,
        )

    async def execute(
        self, ticket: ScanTicket, *, scope: str, correlation_id: str
    ) -> ScanState:
        if ticket.duplicate:
            return ticket.state
        if not await self._store.transition(
            ticket.scan_run_id, expected=ScanState.QUEUED, target=ScanState.RUNNING
        ):
            return ScanState.SKIPPED_DUPLICATE
        try:
            result = await self._pipeline.run(
                scope=scope, correlation_id=correlation_id
            )
        except Exception as exc:
            await self._store.transition(
                ticket.scan_run_id,
                expected=ScanState.RUNNING,
                target=ScanState.FAILED,
                failure_reason=type(exc).__name__,
            )
            return ScanState.FAILED
        target = (
            ScanState.COMPLETED_DEGRADED if result.degraded else ScanState.COMPLETED
        )
        await self._store.transition(
            ticket.scan_run_id, expected=ScanState.RUNNING, target=target
        )
        return target

    async def status(self, scan_run_id: str) -> ScanTicket | None:
        return await self._store.get(scan_run_id, environment=self._environment)
