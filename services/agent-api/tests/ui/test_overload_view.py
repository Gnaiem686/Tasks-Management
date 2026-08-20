from pathlib import Path
import pytest
WEB=Path(__file__).parents[2]/"src"/"agent_api"/"web"
@pytest.mark.ui
def test_dashboard_renders_one_employee_score_without_factor_scores():
    script=(WEB/"static"/"chat.js").read_text()
    assert "employee.score" in script
    assert "riskChip" in script
    assert "contribution_points" not in script
    assert "calculateScore" not in script
@pytest.mark.ui
def test_risk_state_does_not_depend_on_color_alone():
    script=(WEB/"static"/"chat.js").read_text(); styles=(WEB/"static"/"styles.css").read_text()
    assert '`${level} · ${score}/100`' in script
    assert ".risk-chip.low" in styles and ".risk-chip.critical" in styles
    assert "prefers-reduced-motion" in styles
