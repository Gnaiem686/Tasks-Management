from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jira_mcp_client.transport import (  # noqa: E402
    StreamableHttpJiraMcpTransport,
)

from scripts.jira.cli import (  # noqa: E402
    emit,
    load,
    load_scenario,
    mcp_settings,
    parser,
)
from scripts.jira.rest_cleanup import (  # noqa: E402
    GuardedRestCleanup,
    JiraRestDeleteClient,
)
from scripts.jira.runner import ScenarioCoordinator  # noqa: E402


def main() -> None:
    args = parser("Clean the guarded WRD scenario").parse_args()
    if args.live_mcp:
        scenario = load_scenario(args.scenario)
        url, cloud_id, authorization = mcp_settings()
        cloud_resource_id = os.environ.get("ATLASSIAN_CLOUD_RESOURCE_ID")
        if not cloud_resource_id:
            raise ValueError("ATLASSIAN_CLOUD_RESOURCE_ID is required for live cleanup")
        transport = StreamableHttpJiraMcpTransport(
            url=url,
            cloud_id=cloud_id,
            environment="dev",
            authorization_header=authorization,
        )
        result = asyncio.run(
            GuardedRestCleanup(
                transport,
                JiraRestDeleteClient(
                    cloud_resource_id=cloud_resource_id,
                    authorization=authorization,
                ),
            ).cleanup(
                environment=scenario.environment,
                project_key=scenario.project_key,
                ownership_tag=scenario.ownership_tag,
                correlation_id=f"scenario-cleanup-{scenario.scenario_id}",
            )
        )
        emit(result)
        return
    scenario, store = load(args)
    emit(ScenarioCoordinator(store).cleanup(scenario))


if __name__ == "__main__":
    main()
