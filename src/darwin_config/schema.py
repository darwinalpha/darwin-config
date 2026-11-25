"""
Configuration validation: FieldRule / Schema.

Supports inline rules, external schema files (JSON/YAML), and imports inside schema files.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union

from darwin_config.exceptions import ConfigError, ConfigValidationError
from darwin_config.utils import deep_merge, load_config_file, resolve_file_path

TYPE_MAP: Dict[str, Type] = {
    "string": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


@dataclass
class FieldRule:
    """A field validation rule."""

    type: Optional[Type] = None
    required: bool = False
    default: Any = None
    choices: Optional[List[Any]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    validator: Optional[Callable[[Any], None]] = None
    message: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldRule":
        type_name = data.get("type")
        return cls(
            type=TYPE_MAP.get(type_name) if isinstance(type_name, str) else None,
            required=data.get("required", False),
            default=data.get("default"),
            choices=data.get("choices"),
            min=data.get("min"),
            max=data.get("max"),
            pattern=data.get("pattern"),
            message=data.get("message", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.type:
            for name, cls in TYPE_MAP.items():
                if cls is self.type:
                    result["type"] = name
                    break
        if self.required:
            result["required"] = True
        if self.default is not None:
            result["default"] = self.default
        if self.choices is not None:
            result["choices"] = self.choices
        if self.min is not None:
            result["min"] = self.min
        if self.max is not None:
            result["max"] = self.max
        if self.pattern:
            result["pattern"] = self.pattern
        if self.message:
            result["message"] = self.message
        return result


class Schema:
    """A configuration validator."""

    def __init__(self, rules: Dict[str, FieldRule]):
        self.rules = rules
        self._errors: Dict[str, List[str]] = {}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Schema":
        rules: Dict[str, FieldRule] = {}
        for path, rule_data in data.items():
            if isinstance(rule_data, dict):
                rules[path] = FieldRule.from_dict(rule_data)
            elif isinstance(rule_data, str):
                rules[path] = FieldRule(type=TYPE_MAP.get(rule_data, str))
            else:
                raise ConfigError(f"Invalid rule for '{path}': {rule_data!r}")
        return cls(rules)

    @classmethod
    def from_file(cls, filepath: Union[str, Path], base_dir: Optional[Path] = None) -> "Schema":
        resolved = resolve_file_path(str(filepath), base_dir)
        if not resolved.exists():
            raise ConfigError(f"Schema file not found: {resolved}")
        data = load_config_file(resolved)

        # schema files themselves support import
        import_items = data.get("import")
        if import_items:
            paths = [import_items] if isinstance(import_items, str) else import_items
            merged: Dict[str, Any] = {}
            for import_path in paths:
                full_path = resolve_file_path(import_path, resolved.parent)
                if not full_path.exists():
                    raise ConfigError(f"Imported schema not found: {full_path}")
                merged = deep_merge(merged, load_config_file(full_path))
            own_rules = {k: v for k, v in data.items() if k != "import"}
            merged = deep_merge(merged, own_rules)
            return cls.from_dict(merged)

        return cls.from_dict({k: v for k, v in data.items() if not k.startswith("~")})

    @classmethod
    def load(cls, source: Union[Dict[str, Any], str, Path], base_dir: Optional[Path] = None) -> "Schema":
        if isinstance(source, dict):
            return cls.from_dict(source)
        if isinstance(source, (str, Path)):
            return cls.from_file(source, base_dir)
        raise ConfigError(f"Invalid schema source: {type(source)}")

    def validate(self, config: Dict[str, Any]) -> None:
        self._errors.clear()
        for path, rule in self.rules.items():
            self._validate_field(path, self._get_nested(config, path), rule)
        if self._errors:
            raise ConfigValidationError("Configuration validation failed", self._errors)

    def fill_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        result = config.copy()
        for path, rule in self.rules.items():
            if rule.default is None:
                continue
            keys = path.split(".")
            current = result
            for key in keys[:-1]:
                if key not in current or not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]
            if keys[-1] not in current or current[keys[-1]] is None:
                current[keys[-1]] = rule.default
        return result

    def validate_and_fill(self, config: Dict[str, Any]) -> Dict[str, Any]:
        filled = self.fill_defaults(config)
        self.validate(filled)
        return filled

    def _get_nested(self, data: Dict[str, Any], path: str) -> Any:
        value: Any = data
        for key in path.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def _validate_field(self, path: str, value: Any, rule: FieldRule) -> None:
        if rule.required and value is None:
            self._add_error(path, rule.message or f"Field '{path}' is required")
            return
        if value is None:
            return
        if rule.type and not isinstance(value, rule.type):
            self._add_error(
                path,
                f"Field '{path}' has wrong type: expected {rule.type.__name__}, got {type(value).__name__}",
            )
            return
        if rule.choices is not None and value not in rule.choices:
            self._add_error(path, f"Field '{path}' value '{value}' is not in allowed choices: {rule.choices}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if rule.min is not None and value < rule.min:
                self._add_error(path, f"Value {value} is below minimum {rule.min}")
            if rule.max is not None and value > rule.max:
                self._add_error(path, f"Value {value} is above maximum {rule.max}")
        if isinstance(value, str) and rule.pattern and not re.match(rule.pattern, value):
            self._add_error(path, f"Value '{value}' does not match pattern: {rule.pattern}")
        if rule.validator:
            try:
                rule.validator(value)
            except Exception as exc:
                self._add_error(path, str(exc))

    def _add_error(self, path: str, message: str) -> None:
        self._errors.setdefault(path, []).append(message)

    @property
    def errors(self) -> Dict[str, List[str]]:
        return self._errors.copy()

    def __repr__(self) -> str:
        return f"Schema({len(self.rules)} rules)"


def create_schema(rules: Dict[str, Union[FieldRule, Dict[str, Any], str]]) -> Schema:
    parsed: Dict[str, FieldRule] = {}
    for path, rule_data in rules.items():
        if isinstance(rule_data, FieldRule):
            parsed[path] = rule_data
        elif isinstance(rule_data, dict):
            parsed[path] = FieldRule.from_dict(rule_data)
        elif isinstance(rule_data, str):
            parsed[path] = FieldRule(type=TYPE_MAP.get(rule_data, str))
        else:
            raise ValueError(f"Invalid rule data for '{path}': {rule_data}")
    return Schema(parsed)


def validate_config(
    config: Dict[str, Any],
    schema: Optional[Union[Schema, Dict[str, Any], str, Path]] = None,
    base_dir: Optional[Path] = None,
) -> None:
    if schema is None:
        return
    if isinstance(schema, Schema):
        schema.validate(config)
    elif isinstance(schema, dict):
        Schema.from_dict(schema).validate(config)
    elif isinstance(schema, (str, Path)):
        Schema.from_file(schema, base_dir).validate(config)
    else:
        raise ConfigError(f"Invalid schema type: {type(schema)}")


def validate_and_fill(
    config: Dict[str, Any],
    schema: Optional[Union[Schema, Dict[str, Any], str, Path]] = None,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if schema is None:
        return config
    if isinstance(schema, Schema):
        return schema.validate_and_fill(config)
    if isinstance(schema, dict):
        return Schema.from_dict(schema).validate_and_fill(config)
    if isinstance(schema, (str, Path)):
        return Schema.from_file(schema, base_dir).validate_and_fill(config)
    raise ConfigError(f"Invalid schema type: {type(schema)}")


__all__ = [
    "TYPE_MAP",
    "FieldRule",
    "Schema",
    "create_schema",
    "validate_config",
    "validate_and_fill",
]
