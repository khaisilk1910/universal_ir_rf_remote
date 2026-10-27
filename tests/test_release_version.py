"""Release automation must create a matching manifest *before* Git tagging."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "set_version.py"

spec = importlib.util.spec_from_file_location("set_version", SCRIPT)
set_version = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(set_version)


@pytest.fixture
def sample_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"domain": "universal_ir_rf_remote", "name": "Test", "version": "4.1.1"}) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("value,result", [("v4.2.0", "4.2.0"), ("4.2.0", "4.2.0"), ("v0.0.1", "0.0.1")])
def test_accept_stable_version_tags(value, result):
    assert set_version.normalize_version(value) == result


@pytest.mark.parametrize("value", ["", "latest", "v4", "4.2", "v4.2.0-rc1", "04.2.0", "4.2.0;echo hacked", "4.2.0\nnewkey=evil"])
def test_reject_invalid_versions(value):
    with pytest.raises(ValueError):
        set_version.normalize_version(value)


def test_updates_manifest_but_preserves_other_metadata(sample_manifest):
    assert set_version.set_version("v4.2.0", sample_manifest) is True
    result = json.loads(sample_manifest.read_text(encoding="utf-8"))
    assert result == {"domain": "universal_ir_rf_remote", "name": "Test", "version": "4.2.0"}
    assert set_version.set_version("4.2.0", sample_manifest) is False


def test_cannot_go_backwards_and_does_not_modify_file(sample_manifest):
    before = sample_manifest.read_bytes()
    with pytest.raises(ValueError, match="Cannot release"):
        set_version.set_version("v3.9.9", sample_manifest)
    assert sample_manifest.read_bytes() == before


def test_print_tag_never_modifies_manifest(sample_manifest):
    before = sample_manifest.read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--version", "4.2.0", "--print-tag", "--manifest", str(sample_manifest)],
        text=True, capture_output=True, check=True,
    )
    assert result.stdout.strip() == "v4.2.0"
    assert sample_manifest.read_bytes() == before


def test_release_workflow_has_safe_order_and_usable_dispatch():
    workflow_path = ROOT / ".github" / "workflows" / "release.yml"
    raw = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    triggers = workflow.get("on", workflow.get(True))
    assert "workflow_dispatch" in triggers
    assert "push" in triggers
    assert "contents" in workflow["permissions"]
    steps = workflow["jobs"]["release"]["steps"]
    step_names = [step.get("name", "") for step in steps]
    update = step_names.index("Update manifest.json before tagging")
    validation = step_names.index("Validate repository and version")
    tag = step_names.index("Commit version to main and create immutable release tag")
    publish = step_names.index("Publish source release for HACS")
    assert update < validation < tag < publish
    assert "git push origin HEAD:main" in raw
    assert "--verify-tag" in raw
    assert "git push --force" not in raw
