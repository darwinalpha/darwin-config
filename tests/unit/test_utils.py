"""Utility tests: directive recognition, deep merge, paths/globs, file loading."""

import json
from pathlib import Path

import pytest

from darwin_config import ConfigError
from darwin_config.utils import (
    DEFAULT_DIRECTIVES,
    Directives,
    expand_glob_patterns,
    expand_path_vars,
    get_value_by_path,
    is_business_template,
    load_config_file,
    parse_env_var,
    resolve_file_path,
    save_config_file,
    set_value_by_path,
    split_directives,
    unescape_all,
)


# ---------- Directive recognition ----------


def test_default_directive_names_use_singular_import() -> None:
    assert set(DEFAULT_DIRECTIVES) == {"import", "merge", "mount", "schema"}
    assert DEFAULT_DIRECTIVES["import"] == "import"
    assert Directives().logical_of("import") == "import"
    assert len(DEFAULT_DIRECTIVES) == 4  # exactly these four bare keywords are directives


def test_directives_mapping_and_validation() -> None:
    d = Directives({"import": "cfg_import"})
    assert d.key_for("import") == "cfg_import"
    assert d.logical_of("cfg_import") == "import"
    assert d.logical_of("import") is None
    with pytest.raises(ConfigError, match="Unknown directive"):
        Directives({"unknown": "x"})


def test_directive_escape_helpers() -> None:
    d = Directives()
    assert d.is_literal_escape("~import")
    assert d.is_literal_escape("~schema")
    assert not d.is_literal_escape("import")
    assert d.unescape_key("~import") == "import"
    assert d.unescape_key("import") == "import"


def test_split_directives_only_consumes_named_ones() -> None:
    d = Directives()
    config = {"import": ["a.json"], "merge": "${this.x}", "name": "app"}
    business, found = split_directives(config, d, {"import"})
    assert found == {"import": ["a.json"]}
    assert business == {"merge": "${this.x}", "name": "app"}


def test_split_directives_keeps_escape_key_until_final_stage() -> None:
    d = Directives()
    business, found = split_directives({"~import": [1, 2], "import": "x.json"}, d, {"import"})
    assert found == {"import": "x.json"}
    assert business == {"~import": [1, 2]}


def test_unescape_all_recursive() -> None:
    d = Directives()
    raw = {"~import": [1, {"~schema": 2}], "keep": "~not_a_directive"}
    assert unescape_all(raw, d) == {
        "import": [1, {"schema": 2}],
        "keep": "~not_a_directive",
    }


# ---------- Deep merge and paths ----------


def test_deep_merge_recursive_and_override() -> None:
    from darwin_config.utils import deep_merge

    base = {"a": {"x": 1, "y": 2}, "b": 3, "c": {"n": 1}}
    override = {"a": {"y": 20, "z": 30}, "b": None, "c": 99}
    assert deep_merge(base, override) == {
        "a": {"x": 1, "y": 20, "z": 30},
        "b": None,
        "c": 99,
    }
    assert base == {"a": {"x": 1, "y": 2}, "b": 3, "c": {"n": 1}}  # inputs are not mutated


def test_path_helpers() -> None:
    data: dict = {}
    set_value_by_path(data, "a.b.c", 1)
    assert data == {"a": {"b": {"c": 1}}}
    assert get_value_by_path(data, "a.b.c") == 1
    with pytest.raises(KeyError):
        get_value_by_path(data, "a.x")


def test_parse_env_var() -> None:
    assert parse_env_var("TOKEN") == ("TOKEN", None)
    assert parse_env_var("TOKEN:abc:def") == ("TOKEN", "abc:def")
    assert parse_env_var("TOKEN:") == ("TOKEN", None)


def test_expand_path_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIT_BASE", "/from/env")
    assert expand_path_vars("${UNIT_BASE}/a.json", {}) == "/from/env/a.json"
    assert expand_path_vars("${PRESET}/b.json", {"PRESET": "/from/values"}) == "/from/values/b.json"
    assert expand_path_vars("${MISSING:fallback}/c", {}) == "fallback/c"
    assert expand_path_vars("${UNIT_NOPE}/d", {}) == "${UNIT_NOPE}/d"


def test_expand_glob_patterns_dedup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "skip.yaml").write_text("a: 1", encoding="utf-8")
    monkeypatch.setenv("UNIT_DIR", str(tmp_path))
    found = expand_glob_patterns(["${UNIT_DIR}/*.json", "${UNIT_DIR}/*.json"], {})
    assert {p.name for p in found} == {"a.json", "b.json"}
    assert len(found) == 2


def test_resolve_file_path() -> None:
    base = Path("/tmp/base")
    assert resolve_file_path("a.json", base) == base / "a.json"
    assert resolve_file_path(Path("/abs/a.json"), base) == Path("/abs/a.json")


def test_is_business_template() -> None:
    assert is_business_template("{category}/{date}")
    assert not is_business_template("${VAR}")
    assert not is_business_template("plain")


# ---------- File loading ----------


def test_json_load_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    save_config_file(path, {"a": {"b": [1, 2]}})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": {"b": [1, 2]}}
    assert load_config_file(path) == {"a": {"b": [1, 2]}}


def test_yaml_load_save_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "cfg.yaml"
    save_config_file(path, {"a": {"b": [1, 2]}})
    assert load_config_file(path) == {"a": {"b": [1, 2]}}


def test_unsupported_suffix_raises(tmp_path: Path) -> None:
    path = tmp_path / "cfg.toml"
    path.write_text("x = 1", encoding="utf-8")
    with pytest.raises(ConfigError, match="Unsupported config file type"):
        load_config_file(path)
