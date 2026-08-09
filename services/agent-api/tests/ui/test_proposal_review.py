from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_review_shows_exact_assignment_scores_confidence_and_freshness() -> None:
    template = (WEB / "templates" / "chat.html").read_text()
    script = (WEB / "static" / "chat.js").read_text()
    for value in (
        "proposal-id", "proposal-current-assignee", "proposal-new-assignee",
        "current-employee-risk", "predicted-employee-risk",
        "current-project-risk", "predicted-project-risk", "skill-fit-comparison",
        "workload-impact", "dependency-impact", "proposal-confidence",
        "proposal-expiry", "proposal-fingerprint",
    ):
        assert f'id="{value}"' in template
    assert "/api/v1/proposals/" in script
    assert "simulation_payload" in script
    assert ".textContent" in script and "innerHTML" not in script

