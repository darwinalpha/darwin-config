"""Integration tests: multi-file layering, mixed formats, directive cooperation, runtime refs."""

from pathlib import Path

import pytest

from darwin_config import add_config, get_config, init_config
from tests.conftest import write_json, write_yaml


def test_three_layer_import_deep_merge(config_dir: Path) -> None:
    write_json(
        config_dir / "base.json",
        {"server": {"host": "0.0.0.0", "port": 8080, "timeout": 30}, "features": {"cache": True, "metrics": True}},
    )
    write_json(
        config_dir / "common.json",
        {"import": "base.json", "server": {"port": 9090, "workers": 8}, "features": {"cache": False}},
    )
    write_json(
        config_dir / "app.json",
        {"import": ["common.json"], "server": {"timeout": 60}, "app": {"name": "app"}},
    )
    init_config(files=[str(config_dir / "app.json")], mount="config")
    assert get_config("config.server") == {
        "host": "0.0.0.0",
        "port": 9090,
        "timeout": 60,
        "workers": 8,
    }
    assert get_config("config.features") == {"cache": False, "metrics": True}


def test_cross_format_import(config_dir: Path) -> None:
    pytest.importorskip("yaml")
    write_yaml(config_dir / "base.yaml", {"db": {"host": "from-yaml", "port": 1}})
    main_json = write_json(config_dir / "main.json", {"import": "base.yaml", "db": {"port": 2}})
    init_config(files=[str(main_json)], mount="config")
    assert get_config("config.db") == {"host": "from-yaml", "port": 2}

    write_json(config_dir / "base.json", {"db": {"host": "from-json", "port": 3}})
    main_yaml = write_yaml(config_dir / "main.yaml", {"import": "base.json", "db": {"port": 4}})
    init_config(files=[str(main_yaml)], mount="config")
    assert get_config("config.db") == {"host": "from-json", "port": 4}


def test_glob_files_are_all_loaded(config_dir: Path) -> None:
    write_json(config_dir / "part_1.json", {"one": 1})
    write_json(config_dir / "part_2.json", {"two": 2})
    write_json(config_dir / "ignored.yaml", {"three": 3})
    init_config(files=[str(config_dir / "part_*.json")], mount="config")
    assert get_config("config.one") == 1
    assert get_config("config.two") == 2
    assert get_config("config.three") is None


def test_all_directives_cooperate(config_dir: Path) -> None:
    write_json(config_dir / "base.json", {"extra": True})
    write_json(
        config_dir / "main.json",
        {
            "import": "base.json",
            "schema": {
                "name": {"type": "string", "required": True},
                "port": {"type": "integer", "default": 8080},
            },
            "defaults": {"retry": 3, "headers": {"Accept": "json"}},
            "service": {
                "merge": "${this.defaults}",
                "url": "http://${this.name}:${this.port}/v1",
                "retry": 5,
            },
            "name": "svc",
            "budget": "%{calc: ${this.port} * 2 }",
            "~import": [1, 2],
        },
    )
    init_config(files=[str(config_dir / "main.json")], mount="config", validate=True)
    assert get_config("config.extra") is True
    assert get_config("config.port") == 8080
    assert get_config("config.service") == {
        "retry": 5,
        "headers": {"Accept": "json"},
        "url": "http://svc:8080/v1",
    }
    assert get_config("config.budget") == 16160
    assert get_config("config.import") == [1, 2]


def test_directive_remap_end_to_end(config_dir: Path) -> None:
    write_json(config_dir / "base.json", {"from_base": True})
    main = write_json(
        config_dir / "main.json",
        {"cfg_import": "base.json", "import": "ordinary business value"},
    )
    init_config(
        files=[str(main)], mount="config", directives={"import": "cfg_import"}
    )
    assert get_config("config.from_base") is True
    assert get_config("config.import") == "ordinary business value"


def test_root_ref_resolves_later_added_config(config_dir: Path) -> None:
    file = write_json(config_dir / "main.json", {"copy": "${root.extra.token}"})
    init_config(files=[str(file)], mount="config")
    # The reference is evaluated on read, so it sees config appended later
    add_config({"mount": "extra", "token": "late-token"})
    assert get_config("config.copy") == "late-token"
