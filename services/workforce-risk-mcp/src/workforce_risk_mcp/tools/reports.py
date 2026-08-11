from __future__ import annotations

import asyncio
from typing import Any, Protocol

from workforce_risk.reports.generator import DailyRiskReport


class S3Client(Protocol):
    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def generate_presigned_url(
        self, operation: str, Params: dict[str, Any], ExpiresIn: int
    ) -> str: ...


class ImmutableReportStore:
    def __init__(self, *, client: S3Client, bucket: str, environment: str) -> None:
        self._client = client
        self._bucket = bucket
        self._environment = environment

    async def upload(self, report: DailyRiskReport) -> tuple[str, str, str]:
        if report.environment != self._environment:
            raise ValueError("report environment mismatch")
        response = await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=report.object_key,
            Body=report.canonical_bytes(),
            ContentType="application/json",
            ServerSideEncryption="AES256",
            Metadata={"sha256": report.checksum},
        )
        version = response.get("VersionId")
        if not version:
            raise RuntimeError("S3 did not confirm an object version")
        return report.object_key, str(version), report.checksum

    async def authorized_download_url(
        self, *, object_key: str, object_version: str, expires_seconds: int = 300
    ) -> str:
        expected_prefix = f"reports/{self._environment}/"
        if not object_key.startswith(expected_prefix) or expires_seconds > 300:
            raise PermissionError("report download scope is invalid")
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": object_key,
                "VersionId": object_version,
            },
            ExpiresIn=expires_seconds,
        )
