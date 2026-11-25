"""Integration tests: public API lifecycle, standalone loader, error paths."""

from pathlib import Path

import pytest

from darwin_config import (
    ConfigError,
    ConfigLoader,
    ConfigMountError,
    ConfigPathNotFoundError,
    add_alias,
    add_config,
    config_trace,
    get_config,
    get_meta,
    get_trace_summary,
    init_config,
    reload_config,
    set_config,
    try_config,
)
from tests.conftest import write_json


def test_full_lifecycle(config_dir: Path) -> None:
    settings = write_json(config_dir / "settings.json", {"server": {"host": "a", "port": 1}, "fallback": "f"})
    init_config(files=[str(settings)], mount="config")

    assert get_config("config.server.host") == "a"
    assert get_config()["config"]["server"]["port"] == 1
    assert try_config("config.nope", "config.fallback", default="d") == "f"

    adapter = write_json(
        config_dir / "adapter.json",
        {"mount": "adapter.demo", "auth": {"token": "tok"}},
    )
    add_config(str(adapter), mount="primary.demo")
    assert get_config("adapter.demo.auth.token") == "tok"
    assert get_config("primary.demo.auth.token") == "tok"
    assert "adapter.json" in config_trace("primary.demo.auth.token")

    set_config("primary.demo.auth.token", "new")
    assert get_config("adapter.demo.auth.token") == "new"
    assert get_meta("adapter.demo.auth.token")["source"] == "user"
    assert get_trace_summary()["user"] >= 1


def test_add_config_dict_and_root_alias(config_dir: Path) -> None:
    settings = write_json(config_dir / "s.json", {"name": "app"})
    init_config(files=[str(settings)], mount="config")
    add_config({"mount": "runtime.cache", "ttl": 60, "copy": "${root.config.name}"})
    assert get_config("runtime.cache.ttl") == 60
    assert get_config("runtime.cache.copy") == "app"


def test_reload_replays_add_config(config_dir: Path) -> None:
    settings = write_json(config_dir / "s.json", {"v": 1})
    init_config(files=[str(settings)], mount="config")
    add_config({"mount": "extra", "v": 2})
    set_config("config.v", 99)
    assert get_config("config.v") == 99

    write_json(settings, {"v": 10})
    state = reload_config()
    assert state["config"]["v"] == 10
    assert state["extra"]["v"] == 2  # add_config was replayed


def test_add_alias_public_api(config_dir: Path) -> None:
    file = write_json(config_dir / "s.json", {"server": {"host": "a"}})
    init_config(files=[str(file)], mount="config")

    add_alias("primary", "config")
    assert get_config("primary.server.host") == "a"
    set_config("primary.server.host", "b")
    assert get_config("config.server.host") == "b"

    # The target may not exist yet and can be filled in later via add_config
    add_alias("late", "future.path")
    add_config({"mount": "future", "path": {"value": 42}})
    assert get_config("late.value") == 42

    with pytest.raises(ConfigMountError, match="already exists"):
        add_alias("primary", "config")


def test_config_loader_is_independent(config_dir: Path) -> None:
    file = write_json(config_dir / "s.json", {"a": 1})
    data = ConfigLoader(config_files=[str(file)], mount="cfg").load()
    assert data == {"cfg": {"a": 1}}
    with pytest.raises(RuntimeError, match="init_config"):
        get_config("cfg.a")


def test_error_paths(config_dir: Path) -> None:
    with pytest.raises(RuntimeError, match="init_config"):
        get_config("x")
    with pytest.raises(RuntimeError, match="init_config"):
        add_config({"a": 1})
    with pytest.raises(ConfigError, match="Config file not found"):
        init_config(files=[str(config_dir / "s.json")], mount="config")
        add_config(config_dir / "missing.json")

    file = write_json(config_dir / "s.json", {"a": 1})
    init_config(files=[str(file)], mount="config")
    with pytest.raises(ConfigPathNotFoundError):
        get_config("config.missing", raise_on_not_found=True)
