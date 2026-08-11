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
from scripts.jira.mcp_scenario import RovoScenarioSeeder  # noqa: E402
from scripts.jira.runner import ScenarioCoordinator  # noqa: E402
from scripts.jira.scenario import scenario_at_step  # noqa: E402


def main() -> None:
    args = parser("Advance the guarded WRD scenario", step=True).parse_args()
    if args.live_mcp:
        scenario = scenario_at_step(load_scenario(args.scenario), args.step)
        url, cloud_id, authorization = mcp_settings()
        transport = StreamableHttpJiraMcpTransport(
            url=url,
            cloud_id=cloud_id,
            environment="dev",
            authorization_header=authorization,
        )
        result = asyncio.run(
            RovoScenarioSeeder(transport).seed(
                scenario,
                correlation_id=f"scenario-step-{args.step}",
                blocker_field_id="customfield_10042",
            )
        )
        emit({**result.model_dump(), "current_step": args.step})
        return
    scenario, store = load(args)
    result = ScenarioCoordinator(store).advance(scenario, args.step)
    emit({**result.model_dump(), "current_step": store.current_step})


if __name__ == "__main__":
    main()
