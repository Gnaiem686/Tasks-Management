from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

ROOT = Path(__file__).parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_separate_process_streamable_http_returns_exact_score() -> None:
    port = free_port()
    environment = os.environ.copy()
    environment.update(
        {
            "WORKFORCE_MCP_HOST": "127.0.0.1",
            "WORKFORCE_MCP_PORT": str(port),
            "APP_ENVIRONMENT": "dev",
            "SCORING_CONFIG_PATH": str(ROOT / "config" / "scoring" / "v1.yaml"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "workforce_risk_mcp.server"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        deadline = time.monotonic() + 10
        while True:
            try:
                async with (
                    streamable_http_client(url) as (read, write, _),
                    ClientSession(read, write) as session,
                ):
                    await session.initialize()
                    scenario = json.loads(
                        (
                            ROOT / "tests/fixtures/scenarios/overloaded_employee.json"
                        ).read_text()
                    )
                    result = await session.call_tool(
                        "score_employee_overload",
                        arguments={
                            "request": {
                                "schema_version": "1.0",
                                "environment": "dev",
                                "correlation_id": "corr-real-transport",
                                "deadline_at": "2099-01-01T00:00:00Z",
                                "scored_at": "2026-08-06T12:00:00Z",
                                "input": scenario,
                            }
                        },
                    )
                    assert result.isError is False
                    block = result.content[0]
                    assert isinstance(block, TextContent)
                    payload = json.loads(block.text)
                    assert payload["correlation_id"] == "corr-real-transport"
                    assert payload["result"]["score"] == 88
                    assert payload["result"]["level"] == "critical"
                    assert payload["result"]["confidence"] == "high"
                    assert payload["result"]["factors"]
                    assert payload["result"]["evidence_references"]
                    assert (
                        payload["result"]["scoring_model_version"]
                        == "employee-overload-v1"
                    )
                    return
            except Exception:
                if process.poll() is not None or time.monotonic() >= deadline:
                    output = process.stdout.read() if process.stdout else ""
                    pytest.fail(
                        f"separate MCP process did not become usable; output={output}"
                    )
                await __import__("asyncio").sleep(0.1)
    finally:
        process.terminate()
        process.wait(timeout=5)
