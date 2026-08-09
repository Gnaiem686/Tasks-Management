from __future__ import annotations

import asyncio
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
from scripts.jira.mcp_scenario import RovoScenarioVerifier  # noqa: E402
from scripts.jira.runner import ScenarioCoordinator  # noqa: E402


def main() -> None:
    args = parser("Verify the guarded WRD scenario").parse_args()
    if args.live_mcp:
        scenario = load_scenario(args.scenario)
        url, cloud_id, authorization = mcp_settings()
        transport = StreamableHttpJiraMcpTransport(
            url=url,
            cloud_id=cloud_id,
            environment="dev",
            authorization_header=authorization,
        )
        live_result = asyncio.run(
            RovoScenarioVerifier(transport).verify(
                scenario,
                correlation_id=f"scenario-verify-{scenario.scenario_id}",
                blocker_field_id="customfield_10042",
            )
        )
        emit(live_result)
        if not live_result.valid:
            raise SystemExit(1)
        return
    scenario, store = load(args)
    offline_result = ScenarioCoordinator(store).verify(scenario)
    emit(offline_result)
    if not offline_result.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
