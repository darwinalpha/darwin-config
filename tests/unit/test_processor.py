"""Unit tests for file-level directive processors."""

from pathlib import Path

import pytest

from darwin_config import ConfigCircularReferenceError, ConfigError
from darwin_config.processor import (
    process_file_import,
    process_file_merge,
    process_file_schema,
    process_file_this_refs,
)
from darwin_config.utils import Directives


def test_process_file_import_basic(tmp_path: Path) -> None:
    (tmp_path / "base.json").write_text('{"a": 1, "nested": {"x": 1}}', encoding="utf-8")
    result = process_file_import(
        {"import": "base.json", "b": 2, "nested": {"y": 2}},
        tmp_path,
        directives=Directives(),
    )
    assert result == {"a": 1, "b": 2, "nested": {"x": 1, "y": 2}}


def test_process_file_import_nested_object(tmp_path: Path) -> None:
    (tmp_path / "db.json").write_text('{"host": "db", "port": 5432}', encoding="utf-8")
    result = process_file_import(
        {"database": {"import": "db.json", "port": 6000}},
        tmp_path,
        directives=Directives(),
    )
    assert result == {"database": {"host": "db", "port": 6000}}


def test_process_file_import_missing_file_is_tolerant(tmp_path: Path) -> None:
    result = process_file_import(
        {"import": "does-not-exist.json", "keep": 1}, tmp_path, directives=Directives()
    )
    assert result == {"keep": 1}


def test_process_file_import_invalid_type(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="import must be string or list"):
        process_file_import({"import": 123}, tmp_path, directives=Directives())


def test_process_file_import_circular(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text('{"import": "b.json"}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"import": "a.json"}', encoding="utf-8")
    with pytest.raises(ConfigCircularReferenceError):
        process_file_import({"import": "a.json"}, tmp_path, directives=Directives())


def test_process_file_schema_skip_and_fill() -> None:
    config = {"schema": {"x": {"type": "integer", "default": 1}}, "y": 2}
    assert process_file_schema(config, validate=False, directives=Directives()) == {"y": 2}
    assert process_file_schema(config, validate=True, directives=Directives()) == {"x": 1, "y": 2}


def test_process_file_merge_multiple_sources() -> None:
    config = {
        "tpl": {"a": 1, "nested": {"x": 1}},
        "tpl2": {"b": 2, "nested": {"y": 2}},
        "job": {"merge": ["${this.tpl}", "${this.tpl2}"], "a": 9},
    }
    result = process_file_merge(config, directives=Directives())
    assert result["job"] == {"a": 9, "b": 2, "nested": {"x": 1, "y": 2}}


def test_process_file_merge_missing_source_tolerant() -> None:
    config = {"job": {"merge": "${this.nope}", "a": 1}}
    assert process_file_merge(config, directives=Directives())["job"] == {"a": 1}


def test_process_file_merge_circular() -> None:
    config = {"loop": {"merge": "${this.loop}"}}
    with pytest.raises(ConfigCircularReferenceError):
        process_file_merge(config, directives=Directives())


def test_process_file_this_refs_chain_and_error() -> None:
    config = {"a": 1, "b": "${this.a}", "c": "${this.b}/v1", "d": "${this.nope}"}
    with pytest.raises(ConfigError, match="This path"):
        process_file_this_refs(config)
    del config["d"]
    result = process_file_this_refs(config)
    assert result == {"a": 1, "b": 1, "c": "1/v1"}
