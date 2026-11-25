"""Public-contract tests: type definitions, exception hierarchy, logging, exported symbols."""

import logging

import darwin_config as dc
from darwin_config.exceptions import (
    ConfigCircularReferenceError,
    ConfigEnvVarError,
    ConfigError,
    ConfigMountError,
    ConfigNotFoundError,
    ConfigPathNotFoundError,
    ConfigValidationError,
)
from darwin_config.logging import get_logger
from darwin_config.types import ConfigFile


def test_config_file_typed_dict_exposes_import_key() -> None:
    assert "import" in ConfigFile.__annotations__
    for name in ("mount", "merge", "schema"):
        assert name in ConfigFile.__annotations__
    # Functional TypedDict syntax allows the Python keyword "import" as a config field name
    sample: ConfigFile = {"import": "base.yaml", "schema": "rules.json"}
    assert sample["import"] == "base.yaml"


def test_exception_hierarchy() -> None:
    for cls in (
        ConfigNotFoundError,
        ConfigValidationError,
        ConfigCircularReferenceError,
        ConfigPathNotFoundError,
        ConfigEnvVarError,
        ConfigMountError,
    ):
        assert issubclass(cls, ConfigError)


def test_validation_error_message_and_errors() -> None:
    error = ConfigValidationError("bad", {"host": ["required"]})
    assert error.errors == {"host": ["required"]}
    assert "host: required" in str(error)


def test_logger_is_cached_standard_logger() -> None:
    logger = get_logger("darwin_config.unit.contracts")
    assert logger is get_logger("darwin_config.unit.contracts")
    assert isinstance(logger, logging.Logger)


def test_public_api_is_minimal_and_complete() -> None:
    expected = {
        "ConfigLoader",
        "init_config",
        "add_config",
        "get_config",
        "set_config",
        "try_config",
        "reload_config",
        "add_alias",
        "get_aliases",
        "has_alias",
        "Schema",
        "FieldRule",
        "create_schema",
        "validate_config",
        "validate_and_fill",
        "get_meta",
        "config_trace",
        "get_trace_summary",
        "ConfigError",
        "ConfigValidationError",
        "ConfigPathNotFoundError",
        "ConfigCircularReferenceError",
        "ConfigMountError",
    }
    assert set(dc.__all__) == expected
    for name in expected:
        assert hasattr(dc, name)

    # Env-var helpers and no-op compatibility functions are not part of the public API
    removed = {
        "load_env",
        "get_env",
        "set_env",
        "clear_config_cache",
        "clear_aliases",
        "clear_trace",
        "get_trace_data",
        "ConfigFile",
        "Directives",
    }
    assert not (removed & set(dc.__all__))
    for name in removed:
        assert not hasattr(dc, name)
