from pathlib import Path
import pytest
WEB=Path(__file__).parents[2]/"src"/"agent_api"/"web"
@pytest.mark.ui
def test_public_demo_hides_reassignment_execution():
    html=(WEB/"templates"/"chat.html").read_text()
    assert "Structured reassignment proposal" not in html
    assert "Approve exact proposal" not in html
