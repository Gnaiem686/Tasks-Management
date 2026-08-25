from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def checksums(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--installed", type=Path, required=True)
    arguments = parser.parse_args()
    source = checksums(arguments.source)
    installed = checksums(arguments.installed)
    if not source or source != installed:
        raise SystemExit("installed UI assets do not match the tested source tree")
    print(f"verified {len(source)} UI assets")


if __name__ == "__main__":
    main()
