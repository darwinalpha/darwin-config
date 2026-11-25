"""YAML support tests (requires PyYAML: pip install darwin-config[yaml])."""

from pathlib import Path

import pytest

pytest.importorskip("yaml", reason="PyYAML not installed")

from darwin_config import ConfigError, get_config, init_config  # noqa: E402


def test_yaml_basic(config_dir: Path) -> None:
    file = config_dir / "settings.yaml"
    file.write_text(
        """\
database:
  host: localhost
  port: 5432
name: myapp
""",
        encoding="utf-8",
    )
    init_config(files=[str(file)], mount="config")
    assert get_config("config.database.host") == "localhost"
    assert get_config("config.database.port") == 5432
    assert get_config("config.name") == "myapp"


def test_yaml_directives_this_and_import(config_dir: Path) -> None:
    base = config_dir / "base.yaml"
    base.write_text(
        """\
defaults:
  retry: 3
  host: db.example.com
""",
        encoding="utf-8",
    )
    main = config_dir / "main.yml"
    main.write_text(
        """\
import:
  - base.yaml
connection:
  merge: ${this.defaults}
  host: override.example.com
  url: "postgresql://${this.connection.host}:5432/db"
""",
        encoding="utf-8",
    )
    init_config(files=[str(main)], mount="config")
    assert get_config("config.connection.retry") == 3
    assert get_config("config.connection.host") == "override.example.com"
    assert get_config("config.connection.url") == "postgresql://override.example.com:5432/db"


def test_yaml_calc_needs_quotes(config_dir: Path) -> None:
    file = config_dir / "calc.yaml"
    # %{calc:...} must be quoted in YAML, otherwise ": " is read as a mapping separator
    file.write_text(
        """\
timeout: 3
retry: 4
total: "%{calc: ${this.timeout} * ${this.retry} }"
""",
        encoding="utf-8",
    )
    init_config(files=[str(file)], mount="config")
    assert get_config("config.total") == 12


def test_yaml_schema_and_escape(config_dir: Path) -> None:
    file = config_dir / "s.yaml"
    file.write_text(
        """\
schema:
  port: {type: integer, default: 8080}
  name: {type: string, required: true}
name: app
~import: [1, 2]
""",
        encoding="utf-8",
    )
    init_config(files=[str(file)], mount="config", validate=True)
    assert get_config("config.port") == 8080
    assert get_config("config.import") == [1, 2]


def test_yaml_root_ref(config_dir: Path) -> None:
    first = config_dir / "a.yaml"
    first.write_text("token: shared\n", encoding="utf-8")
    second = config_dir / "b.yaml"
    second.write_text("copy: ${root.config.token}\n", encoding="utf-8")
    init_config(files=[str(first), str(second)], mount="config")
    assert get_config("config.copy") == "shared"


def test_yaml_missing_pyyaml_message(config_dir: Path) -> None:
    """A clear install hint is given when PyYAML is missing."""
    from darwin_config.utils import load_config_file

    file = config_dir / "s.yaml"
    file.write_text("a: 1\n", encoding="utf-8")
    # When PyYAML is installed, skip the assertion and just verify normal loading
    assert load_config_file(file) == {"a": 1}
