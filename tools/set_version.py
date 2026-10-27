#!/usr/bin/env python3
"""Validate a GitHub release version and sync the Home Assistant manifest.

Run before creating a release tag: HACS downloads the files at that tag.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components" / "universal_ir_rf_remote" / "manifest.json"
VERSION_PATTERN = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def normalize_version(value: str) -> str:
    """Accept vX.Y.Z or X.Y.Z and return the version without the tag prefix."""
    match = VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("Version must look like 4.2.0 or v4.2.0 (three nonnegative integers)")
    return ".".join(match.groups())


def version_tuple(value: str) -> tuple[int, int, int]:
    return tuple(int(segment) for segment in normalize_version(value).split("."))


def set_version(value: str, manifest_path: Path = MANIFEST, *, dry_run: bool = False) -> bool:
    """Update manifest version; reject regressions. Return True if it changed."""
    normalized = normalize_version(value)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_version = manifest.get("version")
    if old_version and version_tuple(normalized) < version_tuple(old_version):
        raise ValueError(f"Cannot release {normalized}: manifest already declares {old_version}")
    if old_version == normalized:
        return False
    manifest["version"] = normalized
    if not dry_run:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Release version, for example v4.2.0")
    parser.add_argument("--manifest", type=Path, default=MANIFEST, help="Path for testing")
    parser.add_argument("--print-tag", action="store_true", help="Only print the normalized Git tag; do not edit files")
    args = parser.parse_args()
    try:
        version = normalize_version(args.version)
        if args.print_tag:
            print(f"v{version}")
            return 0
        changed = set_version(version, args.manifest)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"manifest.json version = {version} ({'updated' if changed else 'already correct'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
