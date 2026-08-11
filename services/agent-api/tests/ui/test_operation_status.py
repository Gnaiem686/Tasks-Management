from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_execution_placeholder_polls_and_handles_stale_or_duplicate_response() -> None:
    template = (WEB / "templates" / "chat.html").read_text()
    script = (WEB / "static" / "chat.js").read_text()
    assert 'id="operation-status"' in template
    assert 'aria-live="polite"' in template
    assert "executing" in script
    assert "setTimeout" in script
    assert "stale" in script
    assert "approvalInFlight" in script
    assert "Jira has not been changed" in script
