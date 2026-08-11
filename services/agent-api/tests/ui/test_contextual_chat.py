from __future__ import annotations

from pathlib import Path

import pytest
from agent_api.main import app
from httpx import ASGITransport, AsyncClient

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
@pytest.mark.asyncio
async def test_contextual_chat_is_accessible_and_has_restrictive_csp() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert 'aria-labelledby="chat-title"' in response.text
    assert '<label for="manager-question">' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'id="chat-citations"' in response.text
    chat_section = response.text.split('aria-labelledby="chat-title"', 1)[1].split(
        'aria-labelledby="proposal-title"', 1
    )[0]
    assert "Approve" not in chat_section


@pytest.mark.ui
def test_client_sends_only_bounded_context_and_renders_safe_text() -> None:
    script = (WEB / "static" / "chat.js").read_text()
    assert "/api/v1/investigations?project_key=WRD" in script
    assert "employee_id" in script
    assert "project_key" in script
    assert ".textContent" in script
    assert "createTextNode" in script
    assert "innerHTML" not in script
    assert "fullEvidence" not in script
    assert "capability_guidance" in script
    assert "correlation_id" in script
