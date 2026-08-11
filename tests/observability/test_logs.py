import json

from workforce_observability.logging import structured_event


def test_structured_logs_keep_correlation_but_redact_secrets() -> None:
    event = json.loads(
        structured_event(
            "jira_call_failed",
            correlation_id="corr-123",
            environment="dev",
            metadata={
                "authorization": "Bearer secret-token",
                "api_key": "top-secret",
                "nested": {"password": "hunter2", "safe_code": "JIRA_TIMEOUT"},
            },
        )
    )

    assert event["correlation_id"] == "corr-123"
    assert event["metadata"]["authorization"] == "<redacted>"
    assert event["metadata"]["api_key"] == "<redacted>"
    assert event["metadata"]["nested"]["password"] == "<redacted>"
    assert event["metadata"]["nested"]["safe_code"] == "JIRA_TIMEOUT"
    assert "secret-token" not in json.dumps(event)


def test_prompt_and_raw_jwt_fields_are_never_logged() -> None:
    event = json.loads(
        structured_event(
            "request_failed",
            correlation_id="corr-456",
            environment="prod",
            metadata={"prompt": "hidden", "raw_jwt": "aaa.bbb.ccc"},
        )
    )

    assert event["metadata"] == {"prompt": "<redacted>", "raw_jwt": "<redacted>"}
