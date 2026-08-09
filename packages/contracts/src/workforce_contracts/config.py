"""Typed, fail-closed environment configuration contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

PRODUCTION_JIRA_PROJECT = "WORKFORCE-PROD"
EXPECTED_EMPLOYEE_IDS = tuple(f"EMP-{index:03d}" for index in range(1, 8))
SECRET_REFERENCE_PREFIXES = ("env://", "k8s-secret://", "secretsmanager://")


class ConfigurationError(ValueError):
    """Raised when configuration is invalid or environments are not isolated."""


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: Literal["allow", "ignore", "forbid"] | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        try:
            return super().model_validate(
                obj,
                strict=strict,
                extra=extra,
                from_attributes=from_attributes,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        except ValidationError as error:
            raise ConfigurationError(str(error)) from error


class JiraCustomFields(StrictConfigModel):
    blocker_category: str = Field(min_length=1)

    @field_validator("blocker_category")
    @classmethod
    def validate_blocker_field(cls, value: str) -> str:
        if not value.startswith("customfield_"):
            raise ValueError("blocker_category must be a raw Jira custom-field ID")
        return value


class JiraConfig(StrictConfigModel):
    site_url: str = Field(pattern=r"^https://[^/]+\.atlassian\.net$")
    allowed_project_keys: list[str] = Field(min_length=1)
    mutation_project_key: str | None
    allow_mutations: bool
    seed_project_keys: list[str]
    cleanup_project_keys: list[str]
    custom_fields: JiraCustomFields
    workforce_label_prefix: str
    allowed_workforce_employee_ids: list[str]

    @field_validator("workforce_label_prefix")
    @classmethod
    def validate_workforce_label_prefix(cls, value: str) -> str:
        if value != "workforce-employee:":
            raise ValueError("workforce label prefix must be workforce-employee:")
        return value

    @field_validator("allowed_workforce_employee_ids")
    @classmethod
    def validate_employee_ids(cls, value: list[str]) -> list[str]:
        if tuple(value) != EXPECTED_EMPLOYEE_IDS:
            raise ValueError("allowed workforce employee IDs must be EMP-001–EMP-007")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        forbidden_operations = set(self.seed_project_keys + self.cleanup_project_keys)
        if PRODUCTION_JIRA_PROJECT in forbidden_operations:
            raise ValueError(f"{PRODUCTION_JIRA_PROJECT} cannot be seeded or cleaned")
        if self.allow_mutations:
            if self.mutation_project_key not in self.allowed_project_keys:
                raise ValueError("mutation project must be in allowed_project_keys")
        elif self.mutation_project_key is not None:
            raise ValueError(
                "mutation_project_key must be null when mutations are disabled"
            )
        return self


class AwsConfig(StrictConfigModel):
    region: str = Field(min_length=1)
    report_bucket: str = Field(min_length=3)
    notification_queue: str = Field(min_length=3)


class AuthConfig(StrictConfigModel):
    api_key_hmac_pepper_ref: str
    allowed_roles: list[Literal["viewer", "manager", "administrator"]]

    @field_validator("api_key_hmac_pepper_ref")
    @classmethod
    def validate_secret_reference(cls, value: str) -> str:
        if not value.startswith(SECRET_REFERENCE_PREFIXES):
            raise ValueError("API-key pepper must use a secret reference")
        return value


class LimitsConfig(StrictConfigModel):
    request_bytes: int = Field(gt=0)
    chat_requests_per_minute: int = Field(gt=0)
    scan_requests_per_hour: int = Field(gt=0)


class ScoringConfigRef(StrictConfigModel):
    version: str = Field(pattern=r"^v[1-9][0-9]*$")


class EnvironmentConfig(StrictConfigModel):
    environment: Literal["dev", "prod", "test"]
    jira: JiraConfig
    aws: AwsConfig
    auth: AuthConfig
    limits: LimitsConfig
    scoring: ScoringConfigRef

    @model_validator(mode="after")
    def validate_environment_safety(self) -> Self:
        if self.environment == "prod" and self.jira.allow_mutations:
            raise ValueError("production mutations are disabled for the MVP")
        return self

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


def load_environment_config(path: Path) -> EnvironmentConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(
            f"cannot read configuration {path}: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise ConfigurationError(f"configuration {path} must contain a mapping")
    return EnvironmentConfig.model_validate(raw)


def validate_environment_isolation(
    dev: EnvironmentConfig, prod: EnvironmentConfig
) -> None:
    overlap = set(dev.jira.allowed_project_keys) & set(prod.jira.allowed_project_keys)
    if overlap:
        raise ConfigurationError(
            f"dev and prod Jira project scopes overlap: {sorted(overlap)}"
        )
    if dev.aws.report_bucket == prod.aws.report_bucket:
        raise ConfigurationError("dev and prod report buckets must differ")
    if dev.aws.notification_queue == prod.aws.notification_queue:
        raise ConfigurationError("dev and prod notification queues must differ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate environment configuration")
    parser.add_argument("--validate", type=Path, required=True)
    args = parser.parse_args()
    config = load_environment_config(args.validate)
    print(f"valid {config.environment} configuration {config.fingerprint()}")


if __name__ == "__main__":
    main()
