from pathlib import Path

import pytest
from agent_api.main import app
from httpx import ASGITransport, AsyncClient

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
@pytest.mark.asyncio
async def test_project_chat_is_accessible_and_csp_restricted() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert 'aria-labelledby="chat-title"' in response.text
    assert '<label for="manager-question">' in response.text
    assert 'aria-live="polite"' in response.text


@pytest.mark.ui
def test_chat_uses_selected_project_bounded_context_and_safe_dom() -> None:
    script = (WEB / "static" / "chat.js").read_text()
    assert "/api/v1/investigations?" in script
    assert "URLSearchParams" in script
    assert "project_key:state.project" in script
    assert ".textContent" in script
    assert "innerHTML" not in script
    assert 'source!=="bedrock"' in script
    assert "project_key=WRD" not in script
