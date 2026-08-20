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
    normalized = "".join(styles.split())
    assert (
        ".dashboard-shell{display:grid;"
        "grid-template-columns:minmax(0,7fr)minmax(22rem,3fr);" in normalized
    )
    assert "@media(max-width:960px){.dashboard-shell{grid-template-columns:1fr;" in normalized
    assert "@media(max-width:620px){.topbar,.project-controls{align-items:stretch;flex-direction:column}.topbar{padding:1rem}.dashboard-shell{padding:.5rem}.dashboard,.dashboard-lower{grid-template-columns:1fr}.summary-cards{grid-template-columns:1fr}" in normalized
    assert ".chat-panel{background:var(--surface);" in normalized
    assert ".chat-composer{position:sticky;bottom:0" in normalized
    assert ".chat-messages{overflow:auto" in normalized


@pytest.mark.ui
def test_public_dashboard_has_no_api_key_or_mutation_control() -> None:
    html = (WEB / "templates" / "chat.html").read_text()
    script = (WEB / "static" / "chat.js").read_text()
    assert 'id="api-key"' not in html
    assert 'id="approve-proposal"' not in html
    assert "Authorization" not in script
