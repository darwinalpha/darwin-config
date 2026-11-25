"""Core tests: basic loading, mounting, env vars, this/root refs, aliases, reload."""

import json
import os
from pathlib import Path

import pytest

from darwin_config import (
    ConfigError,
    ConfigPathNotFoundError,
    add_config,
    config_trace,
    get_config,
    get_meta,
    init_config,
    reload_config,
    set_config,
    try_config,
)
from tests.conftest import write_json


def test_basic_load(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = write_json(config_dir / "settings.json", {"database": {"host": "localhost", "port": 5432}})
    init_config(files=[str(file)], mount="config")
    assert get_config("config.database.host") == "localhost"
    assert get_config("config.database.port") == 5432
    assert get_config("config.missing", default="x") == "x"
    assert get_config("config.missing") is None
    with pytest.raises(ConfigPathNotFoundError):
        get_config("config.missing", raise_on_not_found=True)


def test_multi_file_merge(config_dir: Path) -> None:
    first = write_json(config_dir / "a.json", {"db": {"host": "a", "port": 1}, "x": 1})
    second = write_json(config_dir / "b.json", {"db": {"port": 2}, "y": 2})
    init_config(files=[str(first), str(second)], mount="config")
    assert get_config("config.db") == {"host": "a", "port": 2}
    assert get_config("config.x") == 1
    assert get_config("config.y") == 2


def test_no_mount(config_dir: Path) -> None:
    file = write_json(config_dir / "s.json", {"name": "app"})
    init_config(files=[str(file)])
    assert get_config("name") == "app"
    assert get_config()["name"] == "app"


def test_env_var(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DC_TOKEN", "abc123")
    file = write_json(config_dir / "s.json", {"auth": {"token": "${DC_TOKEN}"}})
    init_config(files=[str(file)], mount="config")
    assert get_config("config.auth.token") == "abc123"


def test_env_var_default_and_values(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DC_TOKEN", raising=False)
    file = write_json(
        config_dir / "s.json",
        {"a": "${DC_TOKEN:fallback}", "b": "${PRESET}", "url": "${HOST:localhost}:${PORT:8080}/v1"},
    )
    init_config(files=[str(file)], mount="config", values={"PRESET": "preset_value"})
    assert get_config("config.a") == "fallback"
    assert get_config("config.b") == "preset_value"
    assert get_config("config.url") == "localhost:8080/v1"


def test_env_var_missing_raises(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DC_MISSING", raising=False)
    file = write_json(config_dir / "s.json", {"token": "${DC_MISSING}"})
    with pytest.raises(ConfigError, match="Environment variable"):
        init_config(files=[str(file)], mount="config")


def test_business_template_preserved(config_dir: Path) -> None:
    file = write_json(config_dir / "s.json", {"path": "{category}/daily/{date}"})
    init_config(files=[str(file)], mount="config")
    assert get_config("config.path") == "{category}/daily/{date}"


def test_this_reference(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {
            "storage": {
                "root": "/data",
                "fetches": "${this.storage.root}/fetches",
                "daily": "${this.storage.fetches}/daily",
            }
        },
    )
    init_config(files=[str(file)], mount="config")
    assert get_config("config.storage.fetches") == "/data/fetches"
    assert get_config("config.storage.daily") == "/data/fetches/daily"


def test_root_reference(config_dir: Path) -> None:
    first = write_json(config_dir / "a.json", {"token": "shared"})
    second = write_json(config_dir / "b.json", {"copy": "${root.config.token}"})
    init_config(files=[str(first), str(second)], mount="config")
    assert get_config("config.copy") == "shared"


def test_calc_expression(config_dir: Path) -> None:
    file = write_json(
        config_dir / "s.json",
        {"timeout": 3, "retry": 4, "total": "%{calc: ${this.timeout} * ${this.retry} }"},
    )
    init_config(files=[str(file)], mount="config")
    assert get_config("config.total") == 12


def test_try_config(config_dir: Path) -> None:
    file = write_json(config_dir / "s.json", {"a": {"b": 42}})
    init_config(files=[str(file)], mount="config")
    assert try_config("config.missing", "config.a.b", default=0) == 42
    assert try_config("config.x.y", default="fallback") == "fallback"


def test_set_config_and_meta(config_dir: Path) -> None:
    file = write_json(config_dir / "s.json", {"value": 1})
    init_config(files=[str(file)], mount="config")
    set_config("config.value", 2)
    assert get_config("config.value") == 2
    meta = get_meta("config.value")
    assert meta["source"] == "user"
    assert "timestamp" in meta


def test_reload(config_dir: Path) -> None:
    file = write_json(config_dir / "s.json", {"version": 1})
    init_config(files=[str(file)], mount="config")
    set_config("config.version", 99)
    assert get_config("config.version") == 99
    write_json(file, {"version": 2})
    reload_config()
    assert get_config("config.version") == 2  # runtime override was cleared


def test_add_config_and_alias(config_dir: Path) -> None:
    settings = write_json(config_dir / "settings.json", {})
    init_config(files=[str(settings)], mount="config")
    adapter = write_json(
        config_dir / "adapter.json",
        {"mount": "adapter.tushare", "auth": {"token": "abc"}},
    )
    add_config(str(adapter), mount="custom.tushare")
    assert get_config("adapter.tushare.auth.token") == "abc"
    assert get_config("custom.tushare.auth.token") == "abc"
    assert str(adapter) in config_trace("adapter.tushare.auth.token")
    set_config("custom.tushare.auth.token", "new")
    assert get_config("adapter.tushare.auth.token") == "new"  # writes through the alias hit the target


def test_add_config_dict_source(config_dir: Path) -> None:
    settings = write_json(config_dir / "settings.json", {})
    init_config(files=[str(settings)], mount="config")
    add_config({"mount": "memory.cfg", "value": "${MEM:7}"})
    assert get_config("memory.cfg.value") == "7"
