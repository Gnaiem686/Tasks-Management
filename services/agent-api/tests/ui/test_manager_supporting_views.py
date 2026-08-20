from pathlib import Path
import pytest
WEB=Path(__file__).parents[2]/"src"/"agent_api"/"web"
@pytest.mark.ui
def test_dashboard_links_summary_alert_progress_workload_and_tasks():
    html=(WEB/"templates"/"chat.html").read_text(); script=(WEB/"static"/"chat.js").read_text()
    for item in ("summary-cards","risk-alerts","project-progress","workload-distribution","task-rows"): assert f'id="{item}"' in html
    assert "/api/v1/dashboard" in script
    assert "task.jira_url" in script
@pytest.mark.ui
def test_tables_and_status_are_accessible():
    html=(WEB/"templates"/"chat.html").read_text(); styles=(WEB/"static"/"styles.css").read_text()
    assert html.count("<caption>")>=2
    assert 'aria-live="polite"' in html
    assert ":focus-visible" in styles
