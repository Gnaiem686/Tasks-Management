from pathlib import Path
import pytest
WEB=Path(__file__).parents[2]/"src"/"agent_api"/"web"
@pytest.mark.ui
def test_public_ui_exposes_no_jira_mutation_controls():
    html=(WEB/"templates"/"chat.html").read_text(); script=(WEB/"static"/"chat.js").read_text()
    assert "approve-proposal" not in html
    assert "/approve" not in script
    assert "editJiraIssue" not in script
