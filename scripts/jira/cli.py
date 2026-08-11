from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pydantic import BaseModel

from scripts.jira.scenario import FileScenarioStore, ScenarioDefinition


def parser(
    description: str, *, step: bool = False, optional_step: bool = False
) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--scenario", type=Path, required=True)
    backend = result.add_mutually_exclusive_group(required=True)
    backend.add_argument(
        "--state-file",
        type=Path,
        help="offline rehearsal state; live Jira uses the dedicated MCP runner",
    )
    backend.add_argument("--live-mcp", action="store_true")
    if step:
        result.add_argument("--step", required=True)
    elif optional_step:
        result.add_argument("--step")
    return result


def load(paths: argparse.Namespace) -> tuple[ScenarioDefinition, FileScenarioStore]:
    scenario = ScenarioDefinition.model_validate_json(paths.scenario.read_text())
    if paths.state_file is None:
        raise ValueError("offline workflow requires --state-file")
    return scenario, FileScenarioStore(paths.state_file)


def load_scenario(path: Path) -> ScenarioDefinition:
    return ScenarioDefinition.model_validate_json(path.read_text())


def mcp_settings() -> tuple[str, str, str]:
    authorization = os.environ.get("ATLASSIAN_MCP_AUTHORIZATION")
    if not authorization:
        raise ValueError("ATLASSIAN_MCP_AUTHORIZATION is required for --live-mcp")
    return (
        os.environ.get("ATLASSIAN_MCP_URL", "https://mcp.atlassian.com/v1/mcp"),
        os.environ.get("ATLASSIAN_CLOUD_ID", "https://gnaiem686.atlassian.net"),
        authorization,
    )


def emit(value: object) -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    print(json.dumps(value, indent=2, sort_keys=True))


REQUIRED_FIELDS = {
    "Blocker Category": "customfield_10042",
    "Labels": "labels",
}
