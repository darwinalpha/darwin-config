"""TOML support tests: built-in reading, directives, native types, optional writing."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from darwin_config import (
    ConfigError,
    ConfigValidationError,
    Schema,
    add_config,
    get_config,
    init_config,
)
from darwin_config.utils import SUPPORTED_SUFFIXES, load_config_file, save_config_file


def test_toml_suffix_registered() -> None:
    assert ".toml" in SUPPORTED_SUFFIXES


def test_toml_read_builtin_no_dependency(config_dir: Path) -> None:
    file = config_dir / "basic.toml"
    file.write_text(
        """\
name = "myapp"

[database]
host = "localhost"
port = 5432
""",
        encoding="utf-8",
    )
    data = load_config_file(file)
    assert data["name"] == "myapp"
    assert data["database"]["port"] == 5432


def test_toml_directives_import_this_merge(config_dir: Path) -> None:
    base = config_dir / "base.toml"
    base.write_text(
        """\
[defaults]
host = "db.example.com"
retry = 3
""",
        encoding="utf-8",
    )
    main = config_dir / "main.toml"
    main.write_text(
        """\
import = "base.toml"

[connection]
merge = "${this.defaults}"
timeout = 10
""",
        encoding="utf-8",
    )
    init_config(files=[str(main)], mount="config")
    assert get_config("config.connection.host") == "db.example.com"
    assert get_config("config.connection.retry") == 3
    assert get_config("config.connection.timeout") == 10


def test_toml_inline_schema(config_dir: Path) -> None:
    file = config_dir / "schema.toml"
    file.write_text(
        """\
name = "test-app"

[schema]
port = { type = "integer", default = 8080 }
name = { type = "string", required = true }
""",
        encoding="utf-8",
    )
    init_config(files=[str(file)], mount="config", validate=True)
    assert get_config("config.port") == 8080  # schema default applied at root
    assert get_config("config.name") == "test-app"


def test_toml_native_datetime(config_dir: Path) -> None:
    file = config_dir / "time.toml"
    file.write_text(
        """\
started = 2026-11-25T10:30:00Z
birthday = 2026-01-02

[schema]
started = { type = "datetime" }
birthday = { type = "date" }
""",
        encoding="utf-8",
    )
    init_config(files=[str(file)], mount="config", validate=True)
    started = get_config("config.started")
    assert isinstance(started, datetime)
    assert started.tzinfo == timezone.utc
    assert get_config("config.birthday") == date(2026, 1, 2)


def test_toml_datetime_schema_type_mismatch() -> None:
    """Schema rejects a string where an integer is declared, regardless of source format."""
    schema = Schema.from_dict({"port": {"type": "integer"}})
    with pytest.raises(ConfigValidationError):
        schema.validate({"port": "8080"})


def test_toml_escape_key_needs_quotes(config_dir: Path) -> None:
    """TOML bare keys cannot contain '~'; the escape must be quoted."""
    file = config_dir / "escape.toml"
    file.write_text(
        """\
"~import" = [1, 2, 3]
""",
        encoding="utf-8",
    )
    init_config(files=[str(file)], mount="config")
    assert get_config("config.import") == [1, 2, 3]


def test_toml_mount_and_alias(config_dir: Path) -> None:
    file = config_dir / "mount.toml"
    file.write_text(
        """\
mount = "real.service"

[auth]
token = "abc"
""",
        encoding="utf-8",
    )
    init_config(files=[], mount="config")
    add_config(str(file), mount="alias.service")
    assert get_config("alias.service.auth.token") == "abc"
    assert get_config("real.service.auth.token") == "abc"


def test_toml_write_requires_optional_dependency(config_dir: Path) -> None:
    tomli_w = pytest.importorskip("tomli_w", reason="tomli-w not installed")
    assert tomli_w is not None
    target = config_dir / "out.toml"
    data = {"name": "demo", "server": {"host": "x", "port": 80}}
    save_config_file(target, data)
    assert load_config_file(target) == data


def test_unsupported_suffix_still_rejected(config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="Unsupported config file type"):
        load_config_file(config_dir / "x.ini")
