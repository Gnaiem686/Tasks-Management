from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

FOUNDATION_KINDS = {
    "ConfigMap",
    "ExternalSecret",
    "Namespace",
    "NetworkPolicy",
    "SecretStore",
    "ServiceAccount",
}


def split_documents(
    documents: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    migrations = [
        document
        for document in documents
        if document.get("kind") == "Job"
        and document.get("metadata", {}).get("name") == "database-migration"
    ]
    if len(migrations) != 1:
        raise ValueError("rendered release must contain exactly one migration Job")
    foundation = [
        document for document in documents if document.get("kind") in FOUNDATION_KINDS
    ]
    application = [
        document
        for document in documents
        if document not in foundation and document not in migrations
    ]
    return foundation, migrations, application


def _write(path: Path, documents: list[dict[str, Any]]) -> None:
    path.write_text(yaml.safe_dump_all(documents, sort_keys=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rendered", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    documents = [
        document
        for document in yaml.safe_load_all(args.rendered.read_text())
        if document
    ]
    foundation, migration, application = split_documents(documents)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    _write(args.output_directory / "foundation.yaml", foundation)
    _write(args.output_directory / "migration.yaml", migration)
    _write(args.output_directory / "application.yaml", application)


if __name__ == "__main__":
    main()
