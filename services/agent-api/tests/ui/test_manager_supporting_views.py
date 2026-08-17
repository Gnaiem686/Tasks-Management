from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_manager_ui_links_alert_report_audit_and_operation_views() -> None:
    html = (ROOT / "templates" / "chat.html").read_text()
    script = (ROOT / "static" / "chat.js").read_text()
    for element in ("alert-inbox", "report-list", "audit-history", "operation-status"):
        assert f'id="{element}"' in html
    assert "/api/v1/alerts" in script
    assert "/api/v1/reports" in script
    assert "/api/v1/audit" in script
    assert "Stale evidence" in script


@pytest.mark.ui
def test_supporting_tables_have_captions_and_status_is_not_color_only() -> None:
    html = (ROOT / "templates" / "chat.html").read_text()
    assert html.count("<caption>") >= 3
    assert 'aria-live="polite"' in html
    assert "Severity" in html and "State" in html
