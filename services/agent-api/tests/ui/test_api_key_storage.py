from pathlib import Path
import pytest
WEB=Path(__file__).parents[2]/"src"/"agent_api"/"web"
@pytest.mark.ui
def test_public_ui_has_no_browser_credential():
    html=(WEB/"templates"/"chat.html").read_text(); script=(WEB/"static"/"chat.js").read_text()
    assert 'id="api-key"' not in html
    assert "Authorization" not in script
    assert "localStorage" not in script
    assert "workforce-chat:" in script
