from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_dashboard_has_project_regions_detail_drawer_and_persistent_chat() -> None:
    html = (WEB / "templates" / "chat.html").read_text()
    for element in (
        "project-select",
        "refresh-dashboard",
        "summary-cards",
        "team-risk-table",
        "risk-alerts",
        "project-progress",
        "workload-distribution",
        "detail-drawer",
        "chat-panel",
        "chat-messages",
        "chat-composer",
    ):
        assert f'id="{element}"' in html


@pytest.mark.ui
def test_public_dashboard_has_no_api_key_or_mutation_control() -> None:
    html = (WEB / "templates" / "chat.html").read_text()
    script = (WEB / "static" / "chat.js").read_text()
    assert 'id="api-key"' not in html
    assert 'id="approve-proposal"' not in html
    assert "Authorization" not in script
