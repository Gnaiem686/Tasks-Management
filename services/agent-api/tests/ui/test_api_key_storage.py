from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_api_key_is_tab_scoped_and_never_put_in_url_or_dom() -> None:
    script = (WEB / "static" / "chat.js").read_text()
    template = (WEB / "templates" / "chat.html").read_text()
    assert "sessionStorage.setItem" in script
    assert "sessionStorage.getItem" in script
    assert "sessionStorage.removeItem" in script
    assert "localStorage" not in script
    assert "Authorization: `Bearer ${apiKey}`" in script
    assert "encodeURIComponent(apiKey)" not in script
    assert 'type="password"' in template
    assert 'autocomplete="off"' in template
