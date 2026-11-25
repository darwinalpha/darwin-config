"""Schema tests: rule parsing, validation, defaults, file loading, convenience functions."""

from pathlib import Path

import pytest

from darwin_config import ConfigError, ConfigValidationError, FieldRule, Schema
from darwin_config.schema import create_schema, validate_and_fill, validate_config


def test_field_rule_roundtrip() -> None:
    rule = FieldRule.from_dict(
        {"type": "integer", "required": True, "default": 1, "min": 0, "max": 10, "message": "bad"}
    )
    assert rule.type is int
    assert rule.required is True
    assert rule.to_dict() == {
        "type": "integer",
        "required": True,
        "default": 1,
        "min": 0,
        "max": 10,
        "message": "bad",
    }


def test_schema_string_shorthand() -> None:
    schema = Schema.from_dict({"name": "string", "count": "integer"})
    schema.validate({"name": "app", "count": 1})
    with pytest.raises(ConfigValidationError):
        schema.validate({"name": "app", "count": "1"})


def test_required_type_choices_range_pattern() -> None:
    schema = create_schema(
        {
            "name": {"type": "string", "required": True, "pattern": "^[a-z]+$"},
            "port": {"type": "integer", "min": 1, "max": 100},
            "mode": {"type": "string", "choices": ["dev", "prod"]},
        }
    )
    with pytest.raises(ConfigValidationError) as exc:
        schema.validate({"name": "Bad1", "port": 200, "mode": "test"})
    errors = exc.value.errors
    assert set(errors) == {"name", "port", "mode"}


def test_custom_validator() -> None:
    def even(value: object) -> None:
        if value % 2:  # type: ignore[operator]
            raise ValueError("must be even")

    schema = Schema({"n": FieldRule(validator=even)})
    schema.validate({"n": 2})
    with pytest.raises(ConfigValidationError, match="must be even"):
        schema.validate({"n": 3})


def test_fill_defaults_nested_and_non_overwrite() -> None:
    schema = create_schema({"db.port": {"type": "integer", "default": 5432}, "name": {"default": "app"}})
    assert validate_and_fill({"db": {"host": "x"}, "name": "custom"}, schema) == {
        "db": {"host": "x", "port": 5432},
        "name": "custom",
    }


def test_validate_and_fill_order() -> None:
    schema = create_schema({"port": {"type": "integer", "default": 80, "min": 1}})
    assert schema.validate_and_fill({}) == {"port": 80}


def test_schema_from_file_with_import(tmp_path: Path) -> None:
    (tmp_path / "base.json").write_text('{"name": {"type": "string", "required": true}}', encoding="utf-8")
    (tmp_path / "rules.json").write_text(
        '{"import": "base.json", "port": {"type": "integer", "default": 80}}', encoding="utf-8"
    )
    schema = Schema.from_file(tmp_path / "rules.json")
    assert set(schema.rules) == {"name", "port"}
    assert schema.validate_and_fill({"name": "app"}) == {"name": "app", "port": 80}
    with pytest.raises(ConfigValidationError):
        schema.validate({"port": 80})


def test_schema_yaml_file(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "rules.yaml"
    path.write_text("port: {type: integer, default: 8080}\n", encoding="utf-8")
    assert Schema.load(path).validate_and_fill({}) == {"port": 8080}


def test_schema_load_invalid_source() -> None:
    with pytest.raises(ConfigError):
        Schema.load(123)  # type: ignore[arg-type]
    with pytest.raises(ConfigError):
        Schema.from_dict({"x": 123})  # type: ignore[dict-item]
    with pytest.raises(ConfigError, match="Schema file not found"):
        Schema.from_file("missing.json")


def test_helper_functions() -> None:
    schema = create_schema({"x": {"type": "integer", "default": 1}})
    validate_config({"x": 2}, schema)
    validate_config({"x": 2}, {"x": "integer"})
    validate_config({"x": 2}, None)
    assert validate_and_fill({}, schema) == {"x": 1}
    assert validate_and_fill({"a": 1}, None) == {"a": 1}
    with pytest.raises(ConfigError):
        validate_config({"x": 1}, 123)  # type: ignore[arg-type]
    with pytest.raises(ConfigError):
        validate_and_fill({}, 123)  # type: ignore[arg-type]


def test_errors_and_repr() -> None:
    schema = create_schema({"x": {"type": "integer", "required": True}})
    assert repr(schema) == "Schema(1 rules)"
    with pytest.raises(ConfigValidationError):
        schema.validate({})
    assert "x" in schema.errors
    assert "x" in schema.errors  # errors are cleared and rebuilt on validate, still readable
