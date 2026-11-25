"""
Environment variable substitution: ${VAR} / ${VAR:default}

Skips ${this.*}, ${root.*}, %{calc:...} and {param} business templates, leaving them to other stages.
"""

import os
import re
from typing import Any, Dict, Optional

from darwin_config.exceptions import ConfigError
from darwin_config.utils import parse_env_var

_ENV_RE = re.compile(r"\$\{([^}]+)\}")
_MAX_DEPTH = 20


def replace_env_vars(
    value: Any,
    variables: Optional[Dict[str, str]] = None,
    _depth: int = 0,
) -> Any:
    """Replace environment variables recursively."""
    if _depth > _MAX_DEPTH:
        raise ConfigError("Too many substitution iterations (possible circular reference)")
    variables = variables or {}

    if isinstance(value, str):
        if "${" not in value:
            return value
        # Business templates / calc / reference expressions are kept as-is
        if value.startswith("{") and value.endswith("}"):
            return value
        if value.startswith("%{calc:") and value.endswith("}"):
            return value
        if value.startswith(("${this.", "${root.")):
            return value

        def resolve(expr: str) -> str:
            name, default = parse_env_var(expr)
            if name.startswith(("this.", "root.")):
                raise _SkipSubstitution()
            if name in variables:
                return variables[name]
            env_value = os.getenv(name)
            if env_value is not None:
                return env_value
            if default is not None:
                return default
            raise ConfigError(f"Environment variable '{name}' not set")

        # Whole-string single reference: return the resolved type directly
        full = _ENV_RE.fullmatch(value)
        if full:
            try:
                return resolve(full.group(1))
            except _SkipSubstitution:
                return value

        # Mixed string
        replaced = False

        def sub(match: "re.Match[str]") -> str:
            nonlocal replaced
            try:
                resolved = resolve(match.group(1))
            except _SkipSubstitution:
                return match.group(0)
            replaced = True
            return resolved

        result = _ENV_RE.sub(sub, value)
        if replaced and "${" in result:
            return replace_env_vars(result, variables, _depth + 1)
        return result

    if isinstance(value, dict):
        return {k: replace_env_vars(v, variables, _depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_env_vars(item, variables, _depth + 1) for item in value]
    return value


class _SkipSubstitution(Exception):
    """Internal marker: skip a non-environment-variable expression."""


__all__ = ["replace_env_vars"]
