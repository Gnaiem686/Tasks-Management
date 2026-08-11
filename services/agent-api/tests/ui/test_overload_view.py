from __future__ import annotations

from pathlib import Path

import pytest
from agent_api.main import app
from httpx import ASGITransport, AsyncClient

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
@pytest.mark.asyncio
async def test_manager_page_has_keyboard_accessible_controls_and_live_regions() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
    html = response.text
    assert '<label for="employee-select">Employee</label>' in html
    assert '<option value="EMP-001">Synthetic Employee 1</option>' in html
    assert '<option value="EMP-002">Synthetic Employee 2</option>' in html
    assert '<option value="EMP-007">Synthetic Employee 7</option>' in html
    assert 'type="submit"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-live="assertive"' in html
    assert 'id="factor-table"' in html
    assert '<th scope="col">Factor</th>' in html


@pytest.mark.ui
def test_ui_client_renders_required_states_without_recomputing_scores() -> None:
    script = (WEB / "static" / "chat.js").read_text()

    assert "result.score" in script
    assert "result.level" in script
    assert "result.confidence" in script
    assert "result.scoring_model_version" in script
    assert "result.evidence_timestamp" in script
    assert "result.factors" in script
    assert "insufficient-data" in script
    assert "Low risk" in script
    assert "High risk" in script
    assert "Critical risk" in script
    assert "Stale evidence" in script
    assert "correlation_id" in script
    assert "fetch(" in script
    assert "calculateScore" not in script


@pytest.mark.ui
def test_risk_labels_and_warnings_do_not_depend_on_color_alone() -> None:
    template = (WEB / "templates" / "chat.html").read_text()
    styles = (WEB / "static" / "styles.css").read_text()

    assert 'id="risk-label"' in template
    assert 'id="freshness-warning"' in template
    assert 'role="status"' in template
    assert ":focus-visible" in styles
    assert "prefers-reduced-motion" in styles
