from __future__ import annotations

import asyncio
import builtins
import importlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import httpx


class FixtureBackend:
    async def list(self, resource: str, namespace: str) -> list[dict[str, Any]]:
        return [
            {
                "name": f"{resource}-healthy",
                "namespace": namespace,
                "ready": True,
                "status": "Running",
                "restarts": 0,
                "replicas": 2,
            }
        ]

    async def query(self, expression: str, *, timeout_seconds: float) -> float:
        return 0.0

    async def read(
        self,
        *,
        service: str,
        namespace: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> builtins.list[str]:
        return [
            json.dumps(
                {
                    "level": "info",
                    "service": service,
                    "environment": namespace,
                    "message": "healthy",
                }
            )
        ]

    async def attributes(self, environment: str) -> dict[str, int]:
        return {"visible": 0, "in_flight": 0, "oldest_age_seconds": 0, "dlq_visible": 0}

    async def inspect(self, source: str, environment: str) -> dict[str, Any]:
        if source == "github_actions":
            return {
                "workflow": "deploy-dev",
                "conclusion": "success",
                "commit": "fixture",
                "completed_at": "2026-08-09T00:00:00Z",
            }
        if source == "release_metadata":
            return {
                "commit": "fixture",
                "image_digests": ["sha256:fixture"],
                "migration_version": "head",
                "deployed_at": "2026-08-09T00:00:00Z",
            }
        return {
            "availability": 1,
            "latency_ms": 10,
            "auth_failures": 0,
            "jql_failures": 0,
            "schema_failures": 0,
            "rate_limits": 0,
            "conflicts": 0,
            "verification_failures": 0,
            "circuit_open": False,
        }


class LiveBackend:
    """Read-only adapters; credentials come from workload identity or mounted tokens."""

    def __init__(self) -> None:
        self._kubernetes_url = os.environ["KUBERNETES_API_URL"].rstrip("/")
        token_path = Path(
            os.getenv(
                "KUBERNETES_TOKEN_FILE",
                "/var/run/secrets/kubernetes.io/serviceaccount/token",
            )
        )
        self._kubernetes_token = token_path.read_text().strip()
        self._prometheus_url = os.environ["PROMETHEUS_URL"].rstrip("/")
        self._loki_url = os.environ["LOKI_URL"].rstrip("/")

    async def list(self, resource: str, namespace: str) -> list[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self._kubernetes_token}"}
        async with httpx.AsyncClient(timeout=5, verify=True) as client:
            response = await client.get(
                f"{self._kubernetes_url}/api/v1/namespaces/{namespace}/{resource}",
                headers=headers,
            )
            response.raise_for_status()
        records = []
        for item in response.json().get("items", []):
            status, metadata = item.get("status", {}), item.get("metadata", {})
            records.append(
                {
                    "name": metadata.get("name"),
                    "namespace": metadata.get("namespace"),
                    "ready": status.get("phase") == "Running"
                    or status.get("readyReplicas", 0) >= 1,
                    "status": status.get("phase", "deployment"),
                    "restarts": sum(
                        container.get("restartCount", 0)
                        for container in status.get("containerStatuses", [])
                    ),
                    "replicas": status.get("readyReplicas"),
                }
            )
        return records

    async def query(self, expression: str, *, timeout_seconds: float) -> float:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(
                f"{self._prometheus_url}/api/v1/query", params={"query": expression}
            )
            response.raise_for_status()
        results = response.json()["data"]["result"]
        return 0.0 if not results else float(results[0]["value"][1])

    async def read(
        self,
        *,
        service: str,
        namespace: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> builtins.list[str]:
        query = f'{{namespace="{namespace}",app="{service}"}}'
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{self._loki_url}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": str(int(start.timestamp() * 1e9)),
                    "end": str(int(end.timestamp() * 1e9)),
                    "limit": limit,
                    "direction": "backward",
                },
            )
            response.raise_for_status()
        return [
            value[1]
            for stream in response.json()["data"]["result"]
            for value in stream.get("values", [])
        ][:limit]

    async def attributes(self, environment: str) -> dict[str, int]:
        boto3 = cast(Any, importlib.import_module("boto3"))
        client = boto3.client("sqs")
        queue_url = os.environ[f"NOTIFICATION_QUEUE_URL_{environment.upper()}"]
        dlq_url = os.environ[f"NOTIFICATION_DLQ_URL_{environment.upper()}"]
        names = [
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
            "ApproximateAgeOfOldestMessage",
        ]
        queue, dlq = await asyncio.gather(
            asyncio.to_thread(
                client.get_queue_attributes, QueueUrl=queue_url, AttributeNames=names
            ),
            asyncio.to_thread(
                client.get_queue_attributes, QueueUrl=dlq_url, AttributeNames=names
            ),
        )
        attrs, dlq_attrs = queue["Attributes"], dlq["Attributes"]
        return {
            "visible": int(attrs.get(names[0], 0)),
            "in_flight": int(attrs.get(names[1], 0)),
            "oldest_age_seconds": int(attrs.get(names[2], 0)),
            "dlq_visible": int(dlq_attrs.get(names[0], 0)),
        }

    async def inspect(self, source: str, environment: str) -> dict[str, Any]:
        urls = {
            "github_actions": os.environ["GITHUB_DEPLOYMENT_STATUS_URL"],
            "release_metadata": os.environ["RELEASE_METADATA_URL"],
            "jira_integration": os.environ["JIRA_INTEGRATION_HEALTH_URL"],
        }
        headers = (
            {"Authorization": f"Bearer {os.environ['GITHUB_READ_TOKEN']}"}
            if source == "github_actions"
            else {}
        )
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                urls[source], params={"environment": environment}, headers=headers
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("diagnostic backend response must be an object")
        return payload


def get_backend() -> FixtureBackend | LiveBackend:
    mode = os.getenv("DEVOPS_BACKEND_MODE", "fixture")
    environment = os.getenv("APP_ENVIRONMENT", "dev")
    if mode == "fixture":
        if environment == "prod":
            raise RuntimeError("fixture DevOps backend is forbidden in production")
        return FixtureBackend()
    if mode == "live":
        return LiveBackend()
    raise RuntimeError("unknown DevOps backend mode")
