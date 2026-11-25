"""
darwin-config

A layered, recursive JSON / YAML / TOML configuration loader.

Zero third-party dependencies in the core. JSON and TOML reading use the
standard library; optional extras add capabilities on demand:
    pip install darwin-config[yaml]      # YAML support
    pip install darwin-config[toml]      # TOML writing
    pip install darwin-config[pydantic]  # typed validation adapter

Configuration syntax:
    import / merge / mount / schema  bare-keyword directives (~ escapes them into plain fields)
    ${this.xxx}                      in-file reference
    ${root.xxx}                      global config-tree reference
    ${VAR:default}                   environment variable
    %{calc: expr}                    restricted arithmetic (quote it in YAML)
"""

from darwin_config.alias import add_alias, get_aliases, has_alias
from darwin_config.exceptions import (
    ConfigCircularReferenceError,
    ConfigError,
    ConfigMountError,
    ConfigPathNotFoundError,
    ConfigValidationError,
)
from darwin_config.loader import (
    ConfigLoader,
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
from darwin_config.schema import (
    FieldRule,
    Schema,
    create_schema,
    validate_and_fill,
    validate_config,
)

__version__ = "0.3.0"

__all__ = [
    # Loading and access
    "ConfigLoader",
    "init_config",
    "add_config",
    "get_config",
    "set_config",
    "try_config",
    "reload_config",
    # Aliases
    "add_alias",
    "get_aliases",
    "has_alias",
    # Validation
    "Schema",
    "FieldRule",
    "create_schema",
    "validate_config",
    "validate_and_fill",
    # Tracing
    "get_meta",
    "config_trace",
    "get_trace_summary",
    # Exceptions
    "ConfigError",
    "ConfigValidationError",
    "ConfigPathNotFoundError",
    "ConfigCircularReferenceError",
    "ConfigMountError",
]
