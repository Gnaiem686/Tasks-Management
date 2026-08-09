from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


@pytest.mark.ui
def test_approval_requires_exact_structured_confirmation_and_idempotency() -> None:
    template = (WEB / "templates" / "chat.html").read_text()
    script = (WEB / "static" / "chat.js").read_text()
    assert 'id="proposal-confirm"' in template
    assert 'type="checkbox"' in template
    assert 'id="approve-proposal"' in template
    assert 'id="reject-proposal"' in template
    assert "crypto.randomUUID()" in script
    assert "expected_version" in script
    assert "idempotency_key" in script
    assert "proposalConfirm.checked" in script
    assert "approvalInFlight" in script
    chat_handler = script.split('chatForm.addEventListener("submit"', 1)[1].split(
        'form.addEventListener("submit"', 1
    )[0]
    assert "/approve" not in chat_handler


@pytest.mark.ui
def test_warning_and_confirmation_are_keyboard_and_non_color_accessible() -> None:
    template = (WEB / "templates" / "chat.html").read_text()
    assert 'for="proposal-confirm"' in template
    assert 'role="alert"' in template
    assert "Approval does not execute Jira" in template

