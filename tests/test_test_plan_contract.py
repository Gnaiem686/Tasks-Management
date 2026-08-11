import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SPEC = REPOSITORY_ROOT / "docs" / "spec.md"
TEST_PLAN = REPOSITORY_ROOT / "docs" / "test-plan.md"
TEST_MAPPING = REPOSITORY_ROOT / "docs" / "test-mapping.md"
REQUIREMENT_ROW = re.compile(r"^\| (?P<id>\d+\.\d+) \|", re.MULTILINE)
MAPPING_ROW = re.compile(r"^\| (?P<id>\d+\.\d+) \|", re.MULTILINE)


def test_every_specification_requirement_has_a_mapping_row() -> None:
    specification_ids = set(REQUIREMENT_ROW.findall(SPEC.read_text(encoding="utf-8")))
    mapping_ids = set(MAPPING_ROW.findall(TEST_MAPPING.read_text(encoding="utf-8")))

    assert len(specification_ids) == 48
    assert mapping_ids == specification_ids


def test_unit_boundary_prohibits_network_and_real_credentials() -> None:
    plan = TEST_PLAN.read_text(encoding="utf-8")

    required_phrases = (
        "no network",
        "no real credentials",
        "Bedrock/LLM",
        "Jira",
        "AWS",
        "Kubernetes",
        "Prometheus",
        "Loki",
        "GitHub",
        "repositories",
    )

    for phrase in required_phrases:
        assert phrase in plan


def test_real_streamable_http_process_test_has_command_and_success_contract() -> None:
    plan = TEST_PLAN.read_text(encoding="utf-8")

    required_phrases = (
        "Agent API and Workforce Risk MCP run as separate real processes",
        "MCP Streamable HTTP",
        "HTTP status",
        "deterministic score",
        "risk level",
        "confidence",
        "factor contributions",
        "evidence references",
        "scoring version",
        "correlation propagation",
        "typed schema",
        "proof of real transport",
        "tests/integration/test_agent_workforce_mcp_streamable_http.py",
    )

    for phrase in required_phrases:
        assert phrase in plan
