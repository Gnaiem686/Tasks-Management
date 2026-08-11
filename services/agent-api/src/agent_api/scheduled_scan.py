from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

from agent_api.routes.scans import get_scan_service


async def run() -> None:
    """Run the same persisted scan pipeline used by the interactive API."""
    service = get_scan_service()
    scope = os.environ["JIRA_PROJECT_KEY"]
    window = datetime.now(UTC).date().isoformat()
    correlation_id = f"scheduled-{scope}-{window}-{uuid4()}"
    ticket = await service.request(
        scope=scope,
        window=window,
        correlation_id=correlation_id,
    )
    if not ticket.duplicate:
        await service.execute(ticket, scope=scope, correlation_id=correlation_id)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
