from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

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


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
