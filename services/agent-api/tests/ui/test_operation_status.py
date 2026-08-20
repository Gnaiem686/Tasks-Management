from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_public_dashboard_only_posts_chat_reads() -> None:
    script = (WEB / "static" / "chat.js").read_text()
    assert 'method:"POST"' in script
    assert "/api/v1/investigations" in script
    assert "/api/v1/proposals" not in script
