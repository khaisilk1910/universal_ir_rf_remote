#!/usr/bin/env python3
"""Lightweight offline HACS repository sanity checks (not HACS or hassfest)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "universal_ir_rf_remote"
NAME = "Universal IR RF Remote Manager"
EXPECTED_REPOSITORY = "khaisilk1910/universal_ir_rf_remote"


def verify(*, strict: bool = False, tag: str | None = None) -> list[str]:
    problems: list[str] = []
    components = ROOT / "custom_components"
    dirs = sorted(p for p in components.iterdir() if p.is_dir())
    if [p.name for p in dirs] != [DOMAIN]:
        problems.append("custom_components/ must contain exactly one integration: " + DOMAIN)
    comp = components / DOMAIN
    manifest = json.loads((comp / "manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    for key in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners"):
        if not manifest.get(key):
            problems.append(f"manifest.json missing {key}")
    if manifest.get("domain") != DOMAIN or manifest.get("name") != NAME:
        problems.append("Manifest identity mismatch")
    if hacs.get("name") != NAME or hacs.get("render_readme") is not True:
        problems.append("hacs.json does not identify repository and README correctly")
    if tag is not None and tag != f"v{manifest['version']}":
        problems.append(f"Git tag {tag!r} does not match manifest version v{manifest['version']}")
    for filename in ("__init__.py", "config_flow.py", "const.py", "library.py", "services.yaml", "sensor.py", "fan.py", "diagnostics.py"):
        if not (comp / filename).is_file():
            problems.append(f"Missing component file: {filename}")
    for lang in ("en", "vi"):
        translations = json.loads((comp / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        if "config" not in translations or "options" not in translations:
            problems.append(f"Translation {lang} missing config or options")
    for name, size in (("icon.png", (256, 256)), ("icon@2x.png", (512, 512)),
                       ("dark_icon.png", (256, 256)), ("dark_icon@2x.png", (512, 512))):
        filepath = comp / "brand" / name
        if not filepath.exists():
            problems.append(f"Missing brand image: {name}")
            continue
        blob = filepath.read_bytes()[:24]
        if not blob.startswith(b"\x89PNG\r\n\x1a\n") or len(blob) < 24:
            problems.append(f"Invalid PNG: {name}")
        elif struct.unpack(">II", blob[16:24]) != size:
            problems.append(f"Incorrect image dimensions: {name}")
    if strict:
        urls = (manifest.get("documentation", ""), manifest.get("issue_tracker", ""))
        if any("YOUR_GITHUB_USERNAME" in url or "OWNER/REPO" in url for url in urls):
            problems.append("Configure GitHub metadata: python tools/configure_repository.py --repo OWNER/REPO")
        if not all(url.startswith("https://github.com/") for url in urls):
            problems.append("Documentation and issue tracker must be GitHub HTTPS URLs")
        if not manifest.get("codeowners") or "YOUR_GITHUB_USERNAME" in str(manifest["codeowners"]):
            problems.append("GitHub codeowner not configured")
        expected_doc = f"https://github.com/{EXPECTED_REPOSITORY}#readme"
        expected_issues = f"https://github.com/{EXPECTED_REPOSITORY}/issues"
        if manifest.get("documentation") != expected_doc:
            problems.append(f"Repository documentation must be {expected_doc}")
        if manifest.get("issue_tracker") != expected_issues:
            problems.append(f"Repository issue tracker must be {expected_issues}")
        if manifest.get("codeowners") != ["@khaisilk1910"]:
            problems.append("Repository code owner must be @khaisilk1910")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Require real GitHub owner and URLs")
    parser.add_argument("--tag", help="Check a tag such as v4.1.1")
    args = parser.parse_args()
    problems = verify(strict=args.strict, tag=args.tag)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    print("PASS: Offline repository sanity checks (not a HACS/hassfest result)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
