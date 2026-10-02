from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lsc_pop.config import PROJECT_ROOT, Config, load_config


@pytest.fixture
def project_copy(tmp_path: Path) -> Path:
    """A throwaway copy of config/ so tests can edit config and mappings freely."""
    shutil.copytree(PROJECT_ROOT / "config", tmp_path / "config")
    return tmp_path


@pytest.fixture
def cfg(project_copy: Path) -> Config:
    return load_config(project_copy / "config" / "config.yaml")


def install_raw(project: Path, source: str, name: str, data: bytes) -> Path:
    """Write a fake raw file under project/data/raw and register it in the manifest."""
    import hashlib
    import json

    path = project / "data" / "raw" / source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    mpath = project / "data" / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {"files": []}
    manifest["files"] = [
        e for e in manifest["files"] if not (e["source_id"] == source and e["file"] == name)
    ] + [{"source_id": source, "file": name, "sha256": hashlib.sha256(data).hexdigest()}]
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest))
    return path
