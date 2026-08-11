from __future__ import annotations

from workforce_risk.scans.service import ScanService, ScanState, ScanTicket


async def request_scan(
    service: ScanService, *, scope: str, window: str, correlation_id: str
) -> ScanTicket:
    return await service.request(
        scope=scope, window=window, correlation_id=correlation_id
    )


async def execute_scan(
    service: ScanService, ticket: ScanTicket, *, scope: str, correlation_id: str
) -> ScanState:
    return await service.execute(ticket, scope=scope, correlation_id=correlation_id)
