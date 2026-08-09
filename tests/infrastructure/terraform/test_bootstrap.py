import re
from pathlib import Path

ROOT = Path(__file__).parents[3]
BOOTSTRAP = ROOT / "infra" / "terraform" / "bootstrap"
SHARED = ROOT / "infra" / "terraform" / "shared"


def combined(directory: Path) -> str:
    return "\n".join(path.read_text() for path in sorted(directory.glob("*.tf")))


def test_state_bucket_is_encrypted_versioned_private_and_recoverable() -> None:
    text = combined(BOOTSTRAP)

    assert "aws_s3_bucket_server_side_encryption_configuration" in text
    assert "aws_kms_key" in text
    assert 'status = "Enabled"' in text
    assert "aws_s3_bucket_public_access_block" in text
    for setting in (
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ):
        assert re.search(rf"{setting}\s*=\s*true", text)
    assert "aws_s3_bucket_lifecycle_configuration" in text
    assert "aws_dynamodb_table" in text


def test_shared_backend_uses_encrypted_s3_lockfile_and_separate_state_key() -> None:
    text = combined(SHARED)

    assert 'backend "s3"' in text
    assert "encrypt      = true" in text
    assert "use_lockfile = true" in text
    assert 'key          = "shared/terraform.tfstate"' in text
    assert "access_key" not in text
    assert "secret_key" not in text


def test_github_oidc_trust_is_repository_and_environment_scoped() -> None:
    text = combined(SHARED)

    assert "token.actions.githubusercontent.com" in text
    assert "Gnaiem686/Tasks-Management" in text
    assert 'for_each = toset(["dev", "prod"])' in text
    assert "environment:${each.key}" in text
    assert '"sts:AssumeRoleWithWebIdentity"' in text
    assert 'actions = ["sts:AssumeRole"]' not in text


def test_shared_foundation_uses_separate_roles_and_immutable_ecr() -> None:
    text = combined(SHARED)

    assert 'for_each = toset(["dev", "prod"])' in text
    assert 'image_tag_mutability = "IMMUTABLE"' in text
    assert "scan_on_push = true" in text
    assert re.search(r"force_delete\s*=\s*false", text)


def test_no_literal_credentials_or_unprotected_sensitive_outputs() -> None:
    text = (combined(BOOTSTRAP) + combined(SHARED)).lower()

    for forbidden in (
        "aws_access_key_id",
        "aws_secret_access_key",
        "password =",
        "private_key =",
    ):
        assert forbidden not in text
    assert "sensitive = true" in text
