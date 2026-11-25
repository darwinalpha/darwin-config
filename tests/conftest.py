"""Shared test fixtures: reset global state."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from darwin_config import loader as loader_module
from darwin_config import alias as alias_module
from darwin_config.node import Node


@pytest.fixture(autouse=True)
def reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (
        ("_root_node", Node()),
        ("_initialized", False),
        ("_mount_point", ""),
        ("_business_values", {}),
        ("_validate_on_load", False),
        ("_base_dir", None),
        ("_add_config_calls", []),
        ("_config_files", []),
        ("_directives", loader_module.Directives()),
    ):
        monkeypatch.setattr(loader_module, name, value)
    monkeypatch.setattr(alias_module, "_root_node", None)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    path = tmp_path / "config"
    path.mkdir()
    return path


def write_json(path: Path, data: Dict[str, Any]) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def write_yaml(path: Path, data: Dict[str, Any]) -> Path:
    yaml = pytest.importorskip("yaml", reason="PyYAML not installed")
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path
