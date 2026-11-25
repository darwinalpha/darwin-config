"""Directive tests: import / merge / schema / ~ escaping / directive remapping."""

import json
from pathlib import Path

import pytest

from darwin_config import (
    ConfigValidationError,
    Schema,
    create_schema,
    get_config,
    init_config,
    validate_and_fill,
    validate_config,
)
from tests.conftest import write_json


def test_import_simple(config_dir: Path) -> None:
    base = write_json(config_dir / "base.json", {"timeout": 30, "retry": 3})
    main = write_json(
        config_dir / "main.json",
        {"import": ["base.json"], "custom": "value"},
    )
    init_config(files=[str(main)], mount="config")
    assert get_config("config.timeout") == 30
    assert get_config("config.retry") == 3
    assert get_config("config.custom") == "value"


def test_import_override_order(config_dir: Path) -> None:
    a = write_json(config_dir / "a.json", {"value": 1, "from": "a"})
    b = write_json(config_dir / "b.json", {"value": 2, "from": "b"})
    main = write_json(config_dir / "main.json", {"import": ["a.json", "b.json"]})
    init_config(files=[str(main)], mount="config")
    assert get_config("config.value") == 2
    assert get_config("config.from") == "b"


def test_import_current_overrides(config_dir: Path) -> None:
    base = write_json(config_dir / "base.json", {"value": 1})
    main = write_json(config_dir / "main.json", {"import": ["base.json"], "value": 99})
    init_config(files=[str(main)], mount="config")
    assert get_config("config.value") == 99


def test_import_nested_and_recursive(config_dir: Path) -> None:
    base = write_json(config_dir / "base.json", {"base": {"value": 1}})
    common = write_json(
        config_dir / "common.json",
        {"import": ["base.json"], "common": {"value": 2}},
    )
    main = write_json(
        config_dir / "main.json",
        {"import": ["common.json"], "database": {"import": ["base.json"], "host": "db"}},
    )
    init_config(files=[str(main)], mount="config")
    assert get_config("config.base.value") == 1
    assert get_config("config.common.value") == 2
    assert get_config("config.database.base.value") == 1
    assert get_config("config.database.host") == "db"


def test_import_circular(config_dir: Path) -> None:
    write_json(config_dir / "a.json", {"import": ["b.json"]})
    write_json(config_dir / "b.json", {"import": ["a.json"]})
    main = write_json(config_dir / "main.json", {"import": ["a.json"]})
    with pytest.raises(Exception, match="Too many import levels"):
        init_config(files=[str(main)], mount="config")


def test_merge_single_and_multiple(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {
            "defaults": {"overwrite": False, "kwargs": {"trade_date": "{date}"}},
            "base": {"timeout": 30, "retry": 3},
            "fetcher": {
                "stock_daily": {
                    "merge": ["${this.defaults}", "${this.base}"],
                    "overwrite": True,
                    "timeout": 60,
                }
            },
        },
    )
    init_config(files=[str(file)], mount="config")
    stock = get_config("config.fetcher.stock_daily")
    assert stock["overwrite"] is True
    assert stock["kwargs"]["trade_date"] == "{date}"
    assert stock["timeout"] == 60
    assert stock["retry"] == 3


def test_merge_nested(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {
            "defaults": {"settings": {"timeout": 30, "retry": 3}},
            "fetcher": {
                "job": {"merge": "${this.defaults}", "settings": {"timeout": 60}}
            },
        },
    )
    init_config(files=[str(file)], mount="config")
    assert get_config("config.fetcher.job.settings") == {"timeout": 60, "retry": 3}


def test_merge_missing_source_is_tolerant(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {"fetcher": {"job": {"merge": "${this.nonexistent}", "timeout": 60}}},
    )
    init_config(files=[str(file)], mount="config")
    assert get_config("config.fetcher.job.timeout") == 60


def test_schema_inline(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {
            "schema": {
                "host": {"type": "string", "required": True},
                "port": {"type": "integer", "default": 5432, "min": 1, "max": 65535},
            },
            "host": "localhost",
        },
    )
    init_config(files=[str(file)], mount="config", validate=True)
    assert get_config("config.port") == 5432
    assert get_config("config.host") == "localhost"


def test_schema_failure(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {"schema": {"port": {"type": "integer", "required": True}}, "host": "localhost"},
    )
    with pytest.raises(ConfigValidationError):
        init_config(files=[str(file)], mount="config", validate=True)


def test_schema_file_reference(config_dir: Path) -> None:
    schema = write_json(
        config_dir / "schema.json",
        {"host": {"type": "string", "required": True}, "port": {"type": "integer", "default": 80}},
    )
    main = write_json(
        config_dir / "s.json",
        {"schema": "schema.json", "host": "localhost"},
    )
    init_config(files=[str(main)], mount="config", validate=True, base_dir=config_dir)
    assert get_config("config.port") == 80


def test_tilde_escape(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {
            "import": ["base.json"],
            "~import": [1, 2, 3],
            "schema": {"x": {"type": "string"}},
            "~schema": {"name": "mysql"},
            "x": "ok",
        },
    )
    write_json(config_dir / "base.json", {"from_import": True})
    init_config(files=[str(file)], mount="config", validate=True)
    assert get_config("config.from_import") is True
    assert get_config("config.import") == [1, 2, 3]  # escaped into a business field
    assert get_config("config.schema") == {"name": "mysql"}  # escaped into a business field


def test_directive_remap(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {"cfg_import": ["base.json"], "import": "plain_value"},
    )
    write_json(config_dir / "base.json", {"from_import": True})
    init_config(
        files=[str(file)],
        mount="config",
        directives={"import": "cfg_import"},
    )
    assert get_config("config.from_import") is True
    assert get_config("config.import") == "plain_value"  # the original directive name becomes a plain field again


def test_schema_helpers() -> None:
    schema = create_schema(
        {
            "name": {"type": "string", "required": True},
            "port": {"type": "integer", "default": 8080},
        }
    )
    filled = validate_and_fill({"name": "app"}, schema)
    assert filled == {"name": "app", "port": 8080}
    validate_config({"name": "app", "port": 80}, schema)
    with pytest.raises(ConfigValidationError):
        validate_config({"name": 123}, schema)
