"""Regression checks for the real public GitHub repository metadata."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/khaisilk1910/universal_ir_rf_remote"


def test_manifest_owner_and_links():
    manifest = json.loads((ROOT / "custom_components/universal_ir_rf_remote/manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "universal_ir_rf_remote"
    assert manifest["documentation"] == REPO + "#readme"
    assert manifest["issue_tracker"] == REPO + "/issues"
    assert manifest["codeowners"] == ["@khaisilk1910"]


def test_codeowners_file_matches_owner():
    assert "* @khaisilk1910" in (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")


def test_hacs_install_instructions_use_real_repo():
    for file in ("README.md", "docs/PUBLISHING.vi.md", "docs/README.vi.md"):
        text = (ROOT / file).read_text(encoding="utf-8")
        assert REPO in text
        assert "GITHUB_OWNER/REPOSITORY" not in text
