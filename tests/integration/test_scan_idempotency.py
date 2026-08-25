from __future__ import annotations

import os
import uuid

import pytest
from workforce_persistence.database import Database
from workforce_persistence.scan_repository import DatabaseScanStore
from workforce_risk.scans.service import PipelineResult, ScanService, ScanState

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)


class Pipeline:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, *, scope: str, correlation_id: str) -> PipelineResult:
        self.calls += 1
        return PipelineResult(False, ("risk-1",), ("alert-1",), "report-1")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_scan_window_runs_pipeline_once() -> None:
    database = Database(DATABASE_URL)
    pipeline = Pipeline()
    service = ScanService(
        environment="test", store=DatabaseScanStore(database), pipeline=pipeline
    )
    window = f"2026-08-09-{uuid.uuid4()}"
    try:
        first = await service.request(
            scope="WRD", window=window, correlation_id="corr-one"
        )
        duplicate = await service.request(
            scope="WRD", window=window, correlation_id="corr-two"
        )
        assert duplicate.duplicate
        assert duplicate.scan_run_id == first.scan_run_id
        assert (
            await service.execute(first, scope="WRD", correlation_id="corr-one")
            is ScanState.COMPLETED
        )
        await service.execute(duplicate, scope="WRD", correlation_id="corr-two")
        assert pipeline.calls == 1
    finally:
        await database.close()
