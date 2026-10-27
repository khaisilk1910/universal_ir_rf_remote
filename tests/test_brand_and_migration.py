"""Validate branding assets, package identity, and safe metadata import."""

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).parents[1]
DOMAIN = "universal_ir_rf_remote"
COMPONENT = ROOT / "custom_components" / DOMAIN


def test_manifest_and_images():
    data = json.loads((COMPONENT / "manifest.json").read_text())
    assert data["domain"] == DOMAIN
    assert data["name"] == "Universal IR RF Remote Manager"
    from tools.set_version import normalize_version
    assert normalize_version(data["version"]) == data["version"]
    for name, size in (("icon.png", (256, 256)), ("icon@2x.png", (512, 512)),
                       ("dark_icon.png", (256, 256)), ("dark_icon@2x.png", (512, 512))):
        with Image.open(COMPONENT / "brand" / name) as icon:
            assert icon.format == "PNG"
            assert icon.size == size


def test_metadata_import_is_exclusive_and_validates_input(tmp_path):
    spec = importlib.util.spec_from_file_location("import_metadata", ROOT / "tools" / "import_metadata.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = tmp_path / "backup.json"
    target = tmp_path / "library.json"
    source.write_text('{"tv":{"power":{"type":"ir"}}}')
    assert mod.import_metadata(source, target) == 1
    assert json.loads(target.read_text())["tv"]["power"]["type"] == "ir"
    with pytest.raises(FileExistsError):
        mod.import_metadata(source, target)
    source.write_text('[1,2,3]')
    with pytest.raises(FileExistsError):
        mod.import_metadata(source, target)
    target.unlink()
    with pytest.raises(ValueError):
        mod.import_metadata(source, target)
    assert not target.exists()
