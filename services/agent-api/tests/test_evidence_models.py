from __future__ import annotations

import pytest
from agent_api.evidence.models import (
    EvidenceCategory,
    EvidencePlan,
    EvidenceScope,
    MissingData,
    UniversalEvidenceBundle,
    calculate_capacity,
)
from pydantic import ValidationError


def test_capacity_semantics_distinguish_capacity_workload_and_headroom() -> None:
    evidence = calculate_capacity(24, 36)

    assert evidence is not None
    assert evidence.configured_capacity_hours == 24
    assert evidence.workload_hours == 36
    assert evidence.available_capacity_hours == 0
    assert evidence.capacity_headroom_hours == -12
    assert evidence.utilization_percent == 150


def test_non_positive_capacity_is_missing_instead_of_guessed() -> None:
    assert calculate_capacity(None, 36) is None
    assert calculate_capacity(0, 36) is None


def test_evidence_plan_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        EvidencePlan.model_validate(
            {
                "scope": "project",
                "entities": [],
                "evidence_categories": ["jira_write"],
                "exhaustive": False,
            }
        )


def test_universal_bundle_is_optional_safe() -> None:
    bundle = UniversalEvidenceBundle(
        correlation_id="corr-1",
        project_key="WFD",
        plan=EvidencePlan(
            scope=EvidenceScope.PROJECT,
            evidence_categories=(EvidenceCategory.SKILLS_AND_SENIORITY,),
        ),
        missing_data=(
            MissingData(
                category=EvidenceCategory.SKILLS_AND_SENIORITY,
                reason="profiles do not document skills",
                entity="project:WFD",
            ),
        ),
    )

    assert bundle.project_snapshot is None
    assert bundle.missing_data[0].required_for_claim is False
