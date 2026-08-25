import os
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPOSITORY_ROOT / "scripts" / "validation" / "check_no_secrets.sh"


def run_scanner(
    target: Path, *, force_grep: bool = False
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if force_grep:
        environment["PATH"] = "/usr/bin:/bin"
    return subprocess.run(
        ["bash", str(SCANNER), str(target)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_scanner_rejects_synthetic_jira_token(tmp_path: Path) -> None:
    fake_token = "ATATT3" + "xFfSyntheticTokenValueForTestingOnly123456"
    (tmp_path / "leaked.env").write_text(
        f"ATLASSIAN_API_TOKEN={fake_token}\n", encoding="utf-8"
    )

    result = run_scanner(tmp_path)

    assert result.returncode != 0
    assert "possible secret" in result.stderr.lower()
    assert fake_token not in result.stdout
    assert fake_token not in result.stderr


def test_scanner_allows_env_example_placeholders(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text(
        "ATLASSIAN_API_TOKEN=replace-through-secret-delivery\n",
        encoding="utf-8",
    )

    result = run_scanner(tmp_path)

    assert result.returncode == 0
    assert "no possible secrets found" in result.stdout.lower()


def test_scanner_rejects_secret_when_ripgrep_is_unavailable(tmp_path: Path) -> None:
    fake_token = "ATATT3" + "xFfSyntheticTokenValueForTestingOnly123456"
    (tmp_path / "leaked.env").write_text(
        f"ATLASSIAN_API_TOKEN={fake_token}\n", encoding="utf-8"
    )

    result = run_scanner(tmp_path, force_grep=True)

    assert result.returncode != 0
    assert "possible secret" in result.stderr.lower()
    assert fake_token not in result.stdout
    assert fake_token not in result.stderr
