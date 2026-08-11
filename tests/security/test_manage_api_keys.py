from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "security" / "manage_api_keys.py"


@pytest.mark.unit
def test_api_key_management_command_exposes_noninteractive_operations() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "create" in result.stdout
    assert "list" in result.stdout
    assert "revoke" in result.stdout
