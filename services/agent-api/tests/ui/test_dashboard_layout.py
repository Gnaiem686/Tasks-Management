from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_dashboard_has_project_regions_detail_drawer_and_persistent_chat() -> None:
    html = (WEB / "templates" / "chat.html").read_text()
    styles = (WEB / "static" / "styles.css").read_text()
    for element in (
        "project-select",
        "refresh-dashboard",
        "dashboard-shell",
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
    for control in (
        "view-all-employees",
        "view-all-alerts",
        "view-all-tasks",
    ):
        assert f'id="{control}"' in html
    assert 'grid-template-columns:minmax(0,70%) minmax(20rem,30%)' in styles
    assert ".dashboard-shell{" in styles
    assert ".dashboard-lower{" in styles
    assert ".chat-panel{" in styles
    assert "overflow:hidden" in styles
    assert ".chat-composer{position:sticky;bottom:0" in styles
    assert ".chat-messages{overflow:auto" in styles


@pytest.mark.ui
def test_public_dashboard_has_no_api_key_or_mutation_control() -> None:
    html = (WEB / "templates" / "chat.html").read_text()
    script = (WEB / "static" / "chat.js").read_text()
    assert 'id="api-key"' not in html
    assert 'id="approve-proposal"' not in html
    assert "Authorization" not in script
