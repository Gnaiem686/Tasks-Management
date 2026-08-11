from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.jira.guards import validate_scenario_scope  # noqa: E402
from scripts.jira.scenario import ScenarioDefinition  # noqa: E402


class EvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    passed: bool
    missing_findings: tuple[str, ...]
    observed_findings: tuple[str, ...]


def evaluate_agent_result(
    scenario: ScenarioDefinition,
    *,
    step_name: str,
    agent_result: dict[str, Any],
) -> tuple[dict[str, str], EvaluationResult]:
    validate_scenario_scope(
        environment=scenario.environment,
        project_key=scenario.project_key,
    )
    step = next((item for item in scenario.steps if item.name == step_name), None)
    if step is None:
        raise ValueError(f"unknown scenario step: {step_name}")
    request = {"project_key": scenario.project_key, "scenario_step": step_name}
    observed = tuple(sorted(set(agent_result.get("findings", []))))
    missing = tuple(sorted(set(step.expected_findings) - set(observed)))
    has_evidence = bool(agent_result.get("evidence_references"))
    has_scores = bool(agent_result.get("scores"))
    return request, EvaluationResult(
        passed=not missing and has_evidence and has_scores,
        missing_findings=missing,
        observed_findings=observed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a dev Agent scenario scan")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--agent-url", required=True)
    parser.add_argument("--api-key", required=True)
    args = parser.parse_args()
    scenario = ScenarioDefinition.model_validate_json(args.scenario.read_text())
    request = {"project_key": scenario.project_key, "scenario_step": args.step}
    response = httpx.post(
        f"{args.agent_url.rstrip('/')}/api/v1/scans",
        json=request,
        headers={"Authorization": f"Bearer {args.api_key}"},
        timeout=30.0,
    )
    response.raise_for_status()
    _, evaluation = evaluate_agent_result(
        scenario,
        step_name=args.step,
        agent_result=response.json(),
    )
    print(evaluation.model_dump_json(indent=2))
    if not evaluation.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
