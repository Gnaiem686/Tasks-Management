import pytest
from workforce_risk.scans.service import (
    PipelineResult,
    ScanService,
    ScanState,
    ScanTicket,
    scan_window_key,
)


class Store:
    def __init__(self) -> None:
        self.ticket = ScanTicket("scan-1", ScanState.QUEUED)
        self.state = ScanState.QUEUED

    async def enqueue(self, **kwargs: str) -> ScanTicket:
        return self.ticket

    async def transition(
        self,
        scan_run_id: str,
        *,
        expected: ScanState,
        target: ScanState,
        failure_reason: str | None = None,
    ) -> bool:
        if self.state is not expected:
            return False
        self.state = target
        return True

    async def get(self, scan_run_id: str) -> ScanTicket | None:
        return ScanTicket(scan_run_id, self.state)


class Pipeline:
    def __init__(self, degraded: bool = False, fail: bool = False) -> None:
        self.degraded = degraded
        self.fail = fail
        self.correlation_id = ""

    async def run(self, *, scope: str, correlation_id: str) -> PipelineResult:
        self.correlation_id = correlation_id
        if self.fail:
            raise TimeoutError("private dependency")
        return PipelineResult(self.degraded, ("risk-1",), ("alert-1",), "report-1")


@pytest.mark.unit
def test_scan_window_key_is_stable_and_scope_specific() -> None:
    assert scan_window_key("dev", "WRD", "2026-08-09") == scan_window_key(
        "dev", "WRD", "2026-08-09"
    )
    assert scan_window_key("dev", "WRD", "2026-08-09") != scan_window_key(
        "prod", "WRD", "2026-08-09"
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("degraded", "fail", "expected"),
    [
        (False, False, ScanState.COMPLETED),
        (True, False, ScanState.COMPLETED_DEGRADED),
        (False, True, ScanState.FAILED),
    ],
)
async def test_scan_state_transitions(
    degraded: bool, fail: bool, expected: ScanState
) -> None:
    store = Store()
    pipeline = Pipeline(degraded, fail)
    service = ScanService(environment="test", store=store, pipeline=pipeline)
    state = await service.execute(store.ticket, scope="WRD", correlation_id="corr-scan")
    assert state is expected
    assert store.state is expected
    assert pipeline.correlation_id == "corr-scan"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duplicate_ticket_does_not_execute_pipeline() -> None:
    store = Store()
    store.ticket = ScanTicket("scan-existing", ScanState.RUNNING, duplicate=True)
    pipeline = Pipeline(fail=True)
    state = await ScanService(
        environment="test", store=store, pipeline=pipeline
    ).execute(store.ticket, scope="WRD", correlation_id="corr-duplicate")
    assert state is ScanState.RUNNING
    assert pipeline.correlation_id == ""
