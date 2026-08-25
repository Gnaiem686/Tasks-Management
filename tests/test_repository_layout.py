import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTest(unittest.TestCase):
    def test_planned_workspace_paths_exist(self) -> None:
        expected_paths = (
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            ".gitignore",
            ".dockerignore",
            "Makefile",
            "README.md",
            "domain/workforce_risk/__init__.py",
            "services/agent-api/pyproject.toml",
            "services/workforce-risk-mcp/pyproject.toml",
            "services/devops-mcp/pyproject.toml",
            "services/notification-worker/pyproject.toml",
            "packages/contracts/pyproject.toml",
            "packages/jira-mcp-client/pyproject.toml",
            "packages/observability/pyproject.toml",
            "packages/persistence/pyproject.toml",
            "infra/terraform/bootstrap",
            "infra/terraform/shared",
            "infra/terraform/environment",
            "infra/kubernetes/base",
            "infra/kubernetes/overlays/dev",
            "infra/kubernetes/overlays/prod",
            "infra/kubernetes/observability",
            "scripts/jira",
            "scripts/scenario",
            "scripts/demo",
            "scripts/validation",
            "tests/contract",
            "tests/integration",
            "tests/e2e",
            "tests/infrastructure",
            "tests/performance",
            "tests/security",
            "docs/validations",
            "docs/runbooks",
        )

        missing = [
            path for path in expected_paths if not (REPOSITORY_ROOT / path).exists()
        ]

        self.assertEqual([], missing, f"Missing planned repository paths: {missing}")


if __name__ == "__main__":
    unittest.main()
