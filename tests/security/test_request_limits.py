from __future__ import annotations

from collections.abc import Generator

import pytest
from agent_api.main import app
from agent_api.security.limits import POLICIES, limiter
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def reset_limiter() -> Generator[None, None, None]:
    limiter.reset()
    yield
    limiter.reset()


@pytest.mark.security
@pytest.mark.asyncio
async def test_oversized_chat_request_is_rejected_safely() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/investigations?project_key=WRD",
            content=b"x" * (POLICIES["investigations"].max_body_bytes + 1),
            headers={
                "X-Correlation-ID": "corr-large",
                "Authorization": "Bearer hidden",
            },
        )
    assert response.status_code == 413
    assert response.json() == {
        "error_code": "REQUEST_TOO_LARGE",
        "correlation_id": "corr-large",
    }
    assert "hidden" not in response.text


@pytest.mark.security
@pytest.mark.asyncio
async def test_manual_scan_rate_limit_returns_429() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = [
            await client.post(
                "/api/v1/scans?project_key=WRD",
                json={"scope": "WRD", "window": "today"},
                headers={"Authorization": "Bearer same-key"},
            )
            for _ in range(POLICIES["scans"].requests + 1)
        ]
    assert responses[-1].status_code == 429
    assert responses[-1].json()["error_code"] == "RATE_LIMITED"
