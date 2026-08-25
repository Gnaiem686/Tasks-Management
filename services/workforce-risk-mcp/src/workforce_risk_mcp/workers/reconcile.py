from __future__ import annotations

import asyncio
import json
import os

from jira_mcp_client.mutation import JiraAssigneeMutationClient
from jira_mcp_client.transport import StreamableHttpJiraMcpTransport
from workforce_persistence.database import Database
from workforce_persistence.execution_repository import DatabaseReconciliationStore
from workforce_risk.proposals.reconciliation import ReconciliationService
from workforce_risk.proposals.state import ProposalState


async def run() -> int:
    database_url = os.environ["DATABASE_URL"]
    environment = os.getenv("APP_ENVIRONMENT", "dev")
    project_keys = set(json.loads(os.environ["JIRA_ALLOWED_PROJECT_KEYS"]))
    database = Database(database_url)
    try:
        reader = JiraAssigneeMutationClient(
            transport=StreamableHttpJiraMcpTransport(
                url=os.getenv("ATLASSIAN_MCP_URL", "https://mcp.atlassian.com/v1/mcp"),
                cloud_id=os.environ["JIRA_CLOUD_ID"],
                environment=environment,
                authorization_header=os.environ["JIRA_MCP_AUTH_HEADER"],
            ),
            environment=environment,
            allowed_project_keys=project_keys,
        )
        results = await ReconciliationService(
            store=DatabaseReconciliationStore(database, environment=environment),
            reader=reader,
        ).run_once(worker_id=os.getenv("HOSTNAME", "reconciliation-worker"))
        # Safe aggregate result only; IDs remain in audit/log correlation records.
        print(
            json.dumps(
                {
                    "processed": len(results),
                    "uncertain": sum(
                        result.state is ProposalState.UNCERTAIN for result in results
                    ),
                }
            )
        )
        return 0
    finally:
        await database.close()


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
