"""Regression tests for repository packaging and HACS distribution metadata."""
import importlib.util
from pathlib import Path
import json

import pytest

ROOT = Path(__file__).parents[1]


def load_script(filename):
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), ROOT / "tools" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_layout_and_metadata():
    verify = load_script("verify_repository.py")
    assert verify.verify() == []
    assert (ROOT / "hacs.json").is_file()
    assert (ROOT / ".github/workflows/validate.yml").is_file()
    assert (ROOT / ".github/workflows/release.yml").is_file()


def test_tag_is_consistent_with_version():
    verify = load_script("verify_repository.py")
    version = json.loads((ROOT / "custom_components/universal_ir_rf_remote/manifest.json").read_text())["version"]
    assert verify.verify(tag=f"v{version}") == []
    assert any("Git tag" in p for p in verify.verify(tag="v1.0.0"))


def test_owner_script_dry_run():
    configure = load_script("configure_repository.py")
    before = (ROOT / "custom_components/universal_ir_rf_remote/manifest.json").read_text()
    metadata = configure.configure("my-org/universal-ir-rf-remote-manager", dry_run=True)
    assert metadata["issue_tracker"] == "https://github.com/my-org/universal-ir-rf-remote-manager/issues"
    assert metadata["codeowners"] == ["@my-org"]
    assert (ROOT / "custom_components/universal_ir_rf_remote/manifest.json").read_text() == before
    with pytest.raises(ValueError):
        configure.configure("bad repo", dry_run=True)
