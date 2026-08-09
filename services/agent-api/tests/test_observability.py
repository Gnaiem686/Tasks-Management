import pytest
from agent_api.main import app
from agent_api.observability import api_metrics
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_api_exposes_bounded_prometheus_metrics() -> None:
    api_metrics.clear()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/health/live", headers={"X-Correlation-ID": "corr-metric"}
        )
        metrics = await client.get("/metrics")

    assert response.status_code == 200
    assert metrics.status_code == 200
    assert "workforce_http_requests_total" in metrics.text
    assert 'service="agent-api"' in metrics.text
    assert "corr-metric" not in metrics.text
