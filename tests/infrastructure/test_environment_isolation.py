from pathlib import Path

ROOT = Path(__file__).parents[1]
TF_ROOT = ROOT.parent / "infra" / "terraform" / "environment"


def _read(name: str) -> str:
    return (TF_ROOT / name).read_text()


def test_rds_is_private_encrypted_backed_up_and_protected() -> None:
    database = _read("database.tf")
    assert "publicly_accessible         = false" in database
    assert "storage_encrypted           = true" in database
    assert "manage_master_user_password = true" in database
    assert "backup_retention_period" in database
    assert "deletion_protection" in database
    assert "aws_db_subnet_group" in database
    assert "aws_security_group.nodes.id" in database


def test_dev_and_prod_have_distinct_database_names_and_release_inputs() -> None:
    terraform = "\n".join(path.read_text() for path in TF_ROOT.glob("*.tf"))
    assert 'environments = toset(["dev", "prod"])' in terraform
    assert 'dev_database_name' in terraform
    assert 'prod_database_name' in terraform
    assert "environment_release_configuration" in terraform
    assert "WORKFORCE-PROD" in terraform
    assert '"WRD"' in terraform


def test_reports_use_separate_private_versioned_encrypted_buckets() -> None:
    storage = _read("storage.tf")
    assert 'for_each = local.environments' in storage
    assert 'aws_s3_bucket_public_access_block' in storage
    assert "block_public_acls       = true" in storage
    assert 'status = "Enabled"' in storage
    assert 'sse_algorithm     = "aws:kms"' in storage
    assert "aws_s3_bucket_lifecycle_configuration" in storage


def test_each_environment_has_queue_dlq_and_redrive_policy() -> None:
    queue = _read("queue.tf")
    assert 'aws_sqs_queue" "notifications_dlq"' in queue
    assert 'aws_sqs_queue" "notifications"' in queue
    assert "deadLetterTargetArn" in queue
    assert "maxReceiveCount" in queue
    assert "sqs_managed_sse_enabled" in queue
    assert "= true" in queue


def test_secret_containers_are_separate_and_contain_no_values() -> None:
    secrets = _read("secrets.tf")
    locals = _read("locals.tf")
    for secret in ("database", "jira-mcp", "api-key-pepper", "initial-api-key"):
        assert secret in locals
    assert "for_each" in secrets
    assert "local.secret_containers" in secrets
    assert "aws_secretsmanager_secret_version" not in secrets
    assert "secret_string" not in secrets


def test_environment_outputs_are_sensitive_and_do_not_expose_credentials() -> None:
    outputs = _read("outputs.tf")
    assert 'sensitive = true' in outputs
    assert "password" not in outputs.lower()
    assert "secret_value" not in outputs.lower()
