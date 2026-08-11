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
from workforce_persistence.database import Database  # noqa: E402
from workforce_persistence.repositories import (  # noqa: E402
    ProfileRepository,
)

from scripts.jira.cli import (  # noqa: E402
    REQUIRED_FIELDS,
    emit,
    load,
    load_scenario,
    mcp_settings,
    parser,
)
from scripts.jira.mcp_scenario import RovoScenarioSeeder  # noqa: E402
from scripts.jira.profile_seed import seed_profiles  # noqa: E402
from scripts.jira.runner import ScenarioCoordinator  # noqa: E402


def main() -> None:
    args = parser("Seed the guarded WRD scenario").parse_args()
    if args.live_mcp:
        scenario = load_scenario(args.scenario)
        url, cloud_id, authorization = mcp_settings()
        transport = StreamableHttpJiraMcpTransport(
            url=url,
            cloud_id=cloud_id,
            environment="dev",
            authorization_header=authorization,
        )
        database_url = os.environ.get("WORKFORCE_DATABASE_URL")
        current_account = os.environ.get("SCENARIO_CURRENT_ASSIGNEE_ID")
        target_account = os.environ.get("SCENARIO_TARGET_ASSIGNEE_ID")
        if not database_url or not current_account or not target_account:
            raise ValueError(
                "live seed requires WORKFORCE_DATABASE_URL and both approved "
                "SCENARIO_*_ASSIGNEE_ID values"
            )

        async def seed_live() -> object:
            database = Database(database_url)
            try:
                async with database.transaction() as session:
                    await seed_profiles(
                        ProfileRepository(session),
                        scenario,
                        account_ids={
                            "current_assignee": current_account,
                            "target_assignee": target_account,
                        },
                    )
                return await RovoScenarioSeeder(transport).seed(
                    scenario,
                    correlation_id=f"scenario-seed-{scenario.scenario_id}",
                    blocker_field_id="customfield_10042",
                )
            finally:
                await database.close()

        result = asyncio.run(seed_live())
        emit(result)
        return
    scenario, store = load(args)
    emit(ScenarioCoordinator(store).seed(scenario, available_fields=REQUIRED_FIELDS))


if __name__ == "__main__":
    main()
