from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from mcp.server.fastmcp import Context, FastMCP
from workforce_persistence.database import Database
from workforce_persistence.repositories import ProfileRepository

from workforce_risk_mcp.tools.profiles import (
    ProfileCapacityUpdate,
    authorize_profile_change,
)
from workforce_risk_mcp.tools.score_overload import (
    ScoreOverloadRequest,
    score_overload,
)

HOST = os.getenv("WORKFORCE_MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("WORKFORCE_MCP_PORT", "8001"))
ENVIRONMENT = os.getenv("APP_ENVIRONMENT", "dev")
CONFIG_PATH = Path(os.getenv("SCORING_CONFIG_PATH", "config/scoring/v1.yaml"))

mcp = FastMCP(
    "Workforce Risk MCP",
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool(name="score_employee_overload")
def score_employee_overload_tool(request: dict[str, Any]) -> dict[str, Any]:
    """Calculate an auditable employee-overload score from structured evidence."""
    validated = ScoreOverloadRequest.model_validate(request)
    response = score_overload(
        validated,
        config_path=CONFIG_PATH,
        service_environment=ENVIRONMENT,
    )
    return response.model_dump(mode="json")


@mcp.tool(name="update_profile_capacity")
async def update_profile_capacity_tool(
    request: dict[str, Any], ctx: Context[Any, Any, Any]
) -> dict[str, Any]:
    """Update authoritative capacity after independent transport authorization."""
    validated = ProfileCapacityUpdate.model_validate(request)
    http_request = ctx.request_context.request
    transport_context = None
    if http_request is not None and hasattr(http_request, "headers"):
        transport_context = http_request.headers.get("X-Workforce-Authorization")
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    database_url = os.getenv("DATABASE_URL")
    if not secret or not database_url:
        raise RuntimeError("protected profile service is not configured")
    verified = authorize_profile_change(
        validated,
        transport_context=transport_context,
        secret=secret.encode(),
        environment=cast(Literal["dev", "prod", "test"], ENVIRONMENT),
        now=datetime.now(UTC),
    )
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            updated = await ProfileRepository(session).update_capacity_audited(
                environment=ENVIRONMENT,
                employee_id=validated.employee_id,
                expected_version=validated.expected_version,
                capacity_hours=validated.weekly_capacity_hours,
                actor_id=verified.actor_id,
                correlation_id=verified.correlation_id,
            )
            if updated is None:
                raise ValueError("profile not found or version conflict")
            return {
                "schema_version": "1.0",
                "environment": updated.environment,
                "correlation_id": verified.correlation_id,
                "employee_id": updated.employee_id,
                "weekly_capacity_hours": updated.weekly_capacity_hours,
                "version": updated.version,
            }
    finally:
        await database.close()


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
