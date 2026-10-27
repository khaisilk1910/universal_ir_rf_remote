#!/usr/bin/env python3
"""Set repository-specific manifest URLs and code owner before publishing.

Example: python tools/configure_repository.py --repo khaisilk1910/universal_ir_rf_remote
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components/universal_ir_rf_remote/manifest.json"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}$")


def configure(repo: str, *, dry_run: bool = False) -> dict:
    if not REPO_PATTERN.fullmatch(repo) or repo.startswith("-"):
        raise ValueError("Use GitHub OWNER/REPOSITORY, for example khaisilk1910/universal_ir_rf_remote")
    owner, _ = repo.split("/", 1)
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["documentation"] = f"https://github.com/{repo}#readme"
    data["issue_tracker"] = f"https://github.com/{repo}/issues"
    data["codeowners"] = [f"@{owner}"]
    if not dry_run:
        MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    data = configure(args.repo, dry_run=args.dry_run)
    print(f"Documentation: {data['documentation']}")
    print(f"Issue tracker:  {data['issue_tracker']}")
    print(f"Codeowners:    {', '.join(data['codeowners'])}")
    if args.dry_run:
        print("Dry run only. No files changed.")


if __name__ == "__main__":
    main()
