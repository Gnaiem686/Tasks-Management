from __future__ import annotations

import pytest
from agent_api.grounding import GroundingValidationError, validate_jira_claims
from agent_api.task_queries import TaskFact

FACTS = (
    TaskFact(
        key="WFD-7",
        summary="Admin dashboard filters and export",
        status="Done",
        assignee="Mohammad",
    ),
    TaskFact(
        key="WFD-1",
        summary="Backend authentication: refresh token support",
        status="In Progress",
        assignee="Mohammad Gnaiem",
    ),
)


def test_accepts_claim_matching_structured_issue_fact() -> None:
    validate_jira_claims(
        "Mohammad is assigned to WFD-7, Admin dashboard filters and export, "
        "which is currently Done.",
        FACTS,
    )


def test_accepts_multiple_correct_issue_summaries_in_one_sentence() -> None:
    validate_jira_claims(
        "WFD-7, Admin dashboard filters and export, is Done, while WFD-1, "
        "Backend authentication: refresh token support, is In Progress.",
        FACTS,
    )


def test_accepts_known_employee_identifier_without_treating_it_as_issue() -> None:
    validate_jira_claims(
        "EMP-004 cannot be classified because its estimate is missing.",
        FACTS,
        referenced_employee_ids={"EMP-004"},
    )


@pytest.mark.parametrize(
    "answer",
    [
        "WFD-99 is Done.",
        "WFD-1, Admin dashboard filters and export, is Done.",
        "WFD-7 is assigned to Mohammad Gnaiem.",
        "WFD-7 is currently In Progress.",
    ],
)
def test_rejects_claim_not_matching_structured_evidence(answer: str) -> None:
    with pytest.raises(GroundingValidationError):
        validate_jira_claims(answer, FACTS)
