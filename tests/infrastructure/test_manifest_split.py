from pathlib import Path

import yaml

from scripts.deployment.split_manifests import split_documents

ROOT = Path(__file__).parents[2]


def test_migration_is_separated_from_application_rollout() -> None:
    documents = [
        doc
        for doc in yaml.safe_load_all(
            (ROOT / "infra" / "kubernetes" / "base" / "workloads.yaml").read_text()
        )
        if doc
    ]
    foundation, migration, application = split_documents(documents)
    assert any(doc["kind"] == "ExternalSecret" for doc in foundation)
    assert [doc["kind"] for doc in migration] == ["Job"]
    assert migration[0]["metadata"]["name"] == "database-migration"
    assert any(doc["kind"] == "Deployment" for doc in application)
    assert all(doc["kind"] != "Job" for doc in application)


def test_unknown_or_duplicate_migration_is_rejected() -> None:
    migration = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": "database-migration"},
    }
    try:
        split_documents([migration, migration])
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("duplicate migration must be rejected")
