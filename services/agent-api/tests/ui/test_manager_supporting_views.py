from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_dashboard_links_summary_alert_progress_workload_and_tasks() -> None:
    html = (WEB / "templates" / "chat.html").read_text()
    script = (WEB / "static" / "chat.js").read_text()
    for item in (
        "summary-cards",
        "risk-alerts",
        "project-progress",
        "workload-distribution",
        "task-rows",
    ):
        assert f'id="{item}"' in html
    assert "/api/v1/dashboard" in script
    assert "task.jira_url" in script
    assert "const EMPLOYEE_PREVIEW_LIMIT=5;" in script
    assert "const ALERT_PREVIEW_LIMIT=4;" in script
    assert "const TASK_PREVIEW_LIMIT=5;" in script
    assert "function openCollectionDrawer(title,items,renderer)" in script
    assert "snapshot.employees.slice(0,EMPLOYEE_PREVIEW_LIMIT)" in script
    assert "snapshot.alerts.slice(0,ALERT_PREVIEW_LIMIT)" in script
    assert "snapshot.tasks.slice(0,TASK_PREVIEW_LIMIT)" in script
    assert 'data-view-all="employees"' in html
    assert 'data-view-all="alerts"' in html
    assert 'data-view-all="tasks"' in html


@pytest.mark.ui
def test_tables_and_status_are_accessible() -> None:
    html = (WEB / "templates" / "chat.html").read_text()
    styles = (WEB / "static" / "styles.css").read_text()
    assert html.count("<caption>") >= 2
    assert 'aria-live="polite"' in html
    assert ":focus-visible" in styles
    assert ".risk-state-good{" in styles
    assert ".risk-state-warning{" in styles
    assert ".risk-state-critical{" in styles
