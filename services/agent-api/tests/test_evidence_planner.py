from __future__ import annotations

import pytest
from agent_api.evidence.models import EvidenceCategory, EvidenceScope
from agent_api.evidence.planner import BedrockEvidencePlanner


@pytest.mark.asyncio
async def test_planner_accepts_previously_unseen_candidate_wording() -> None:
    async def invoke(_prompt: str, _payload: dict[str, object]) -> str:
        return """{
          "scope": "mixed",
          "entities": [{"kind": "employee", "identifier": "EMP-002"}],
          "evidence_categories": ["jira_issues", "workforce_profiles",
            "capacity_and_workload", "skills_and_seniority"],
          "exhaustive": true
        }"""

    plan = await BedrockEvidencePlanner(invoke=invoke).plan(
        question="Who has both the technical fit and enough room to absorb this?",
        project_key="WFD",
        employee_id="EMP-002",
        previous_context=None,
        correlation_id="corr-1",
    )

    assert plan.scope is EvidenceScope.MIXED
    assert EvidenceCategory.SKILLS_AND_SENIORITY in plan.evidence_categories


@pytest.mark.asyncio
async def test_planner_degrades_model_selected_write_category_to_safe_reads() -> None:
    async def invoke(_prompt: str, _payload: dict[str, object]) -> str:
        return (
            '{"scope":"project","entities":[],"evidence_categories":'
            '["jira_write"],"exhaustive":false}'
        )

    plan = await BedrockEvidencePlanner(invoke=invoke).plan(
        question="show project risk",
        project_key="WFD",
        employee_id=None,
        previous_context=None,
        correlation_id="corr-2",
    )

    assert set(plan.evidence_categories) == set(EvidenceCategory)


@pytest.mark.asyncio
async def test_planner_degrades_malformed_json_to_safe_reads() -> None:
    async def invoke(_prompt: str, _payload: dict[str, object]) -> str:
        return "not-json"

    plan = await BedrockEvidencePlanner(invoke=invoke).plan(
        question="What is happening?",
        project_key="WFD",
        employee_id=None,
        previous_context=None,
        correlation_id="corr-malformed",
    )

    assert plan.exhaustive is True


@pytest.mark.asyncio
async def test_planner_preserves_persistent_transport_failure() -> None:
    async def invoke(_prompt: str, _payload: dict[str, object]) -> str:
        raise OSError("Bedrock unavailable")

    with pytest.raises(OSError, match="Bedrock unavailable"):
        await BedrockEvidencePlanner(invoke=invoke, max_attempts=2).plan(
            question="What is happening?",
            project_key="WFD",
            employee_id=None,
            previous_context=None,
            correlation_id="corr-outage",
        )
