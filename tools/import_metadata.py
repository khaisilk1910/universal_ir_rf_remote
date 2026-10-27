"""Safely copy a user-selected command-metadata JSON backup while HA is stopped.

Usage: python3 tools/import_metadata.py --source BACKUP.json --destination NEW.json
The destination must not exist. Never rewrite Home Assistant's config-entry files.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile


def import_metadata(source: Path, destination: Path) -> int:
    if not source.is_file():
        raise FileNotFoundError(f"Source file does not exist: {source}")
    if destination.exists():
        raise FileExistsError(f"Target already exists; refusing to overwrite: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Destination directory does not exist: {destination.parent}")

    raw = source.read_bytes()
    content = json.loads(raw)
    if not isinstance(content, dict) or not all(
        isinstance(device, str) and isinstance(commands, dict)
        and all(isinstance(command, str) for command in commands)
        for device, commands in content.items()
    ):
        raise ValueError("Not a compatible remote command metadata JSON object")

    # Validate and never overwrite a possibly newly-created destination.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as file:
            temp_path = Path(file.name)
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        os.link(temp_path, destination)  # atomic and exclusive
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return sum(len(v) for v in content.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    total = import_metadata(args.source, args.destination)
    print(f"Imported {total} command metadata records to {args.destination}")


if __name__ == "__main__":
    main()
