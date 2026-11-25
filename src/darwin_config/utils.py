"""
Utility functions: file loading (JSON / optional YAML), path handling, deep merge, directive recognition.

The core has zero third-party dependencies; YAML support is provided by the optional PyYAML extra.
"""

import glob as _glob
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from darwin_config.exceptions import ConfigError

# ============================================================
# Directive (reserved word) definitions and recognition
# ============================================================

DEFAULT_DIRECTIVES: Dict[str, str] = {
    "import": "import",
    "merge": "merge",
    "mount": "mount",
    "schema": "schema",
}

# Directives usable at nested levels; mount/schema are valid only at the file's top level
NESTED_DIRECTIVES = frozenset({"import", "merge"})


class Directives:
    """
    Directive-name resolver.

    - By default the bare keywords import / merge / mount / schema are used
    - A mapping can remap them, e.g. {"import": "cfg_import"}
    - Keys starting with ~ are treated as escaped literals (~import -> plain field import)
    """

    def __init__(self, mapping: Optional[Dict[str, str]] = None):
        self.mapping: Dict[str, str] = dict(DEFAULT_DIRECTIVES)
        if mapping:
            unknown = set(mapping) - set(DEFAULT_DIRECTIVES)
            if unknown:
                raise ConfigError(f"Unknown directive names: {sorted(unknown)}")
            self.mapping.update(mapping)
        self._by_key: Dict[str, str] = {v: k for k, v in self.mapping.items()}

    def key_for(self, logical: str) -> str:
        return self.mapping[logical]

    def logical_of(self, key: str) -> Optional[str]:
        return self._by_key.get(key)

    def is_literal_escape(self, key: str) -> bool:
        """An escape key such as ~import."""
        return key.startswith("~") and key[1:] in self._by_key

    def unescape_key(self, key: str) -> str:
        return key[1:] if self.is_literal_escape(key) else key


def split_directives(
    config: Dict[str, Any],
    directives: Directives,
    names: Iterable[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Split a config dict into the requested directives and business fields.

    Args:
        config: the original config dict
        directives: the directive resolver
        names: logical directive names to consume in this stage, e.g. {"import"}

    Returns:
        (business fields, {logical directive name: directive value})

    Notes:
        - ~ escape keys (~import, etc.) are kept as-is; unescape_all() removes the prefix at the end
        - directives not listed in names stay in the business fields for their own stage
    """
    wanted = set(names)
    business: Dict[str, Any] = {}
    found: Dict[str, Any] = {}
    for key, value in config.items():
        logical = directives.logical_of(key)
        if logical is not None and logical in wanted:
            found[logical] = value
        else:
            # Escape keys are kept as-is; unescape_all() handles them at the end of the pipeline
            business[key] = value
    return business, found


def unescape_all(value: Any, directives: Directives) -> Any:
    """Recursively turn all ~directive escape keys back into ordinary fields at the end of the pipeline."""
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, child in value.items():
            new_key = directives.unescape_key(key) if directives.is_literal_escape(key) else key
            result[new_key] = unescape_all(child, directives)
        return result
    if isinstance(value, list):
        return [unescape_all(item, directives) for item in value]
    return value


# ============================================================
# Deep merge / path access
# ============================================================


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge recursively when both sides are dicts; otherwise override wins. None is preserved."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_value_by_path(data: Dict[str, Any], path: str) -> Any:
    """Read a nested value by dot path; raise KeyError when missing."""
    value: Any = data
    for key in path.split("."):
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            raise KeyError(f"Path not found: {path}")
    return value


def set_value_by_path(data: Dict[str, Any], path: str, value: Any) -> None:
    """Write a nested value by dot path."""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def parse_env_var(expr: str) -> Tuple[str, Optional[str]]:
    """Parse VAR or VAR:default (colons are allowed inside the default)."""
    if ":" in expr:
        name, default = expr.split(":", 1)
        return name, default if default else None
    return expr, None


def expand_path_vars(path: str, variables: Dict[str, str]) -> str:
    """Expand ${VAR} / ${VAR:default} in a path; keep the original when missing."""
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replacer(match: "re.Match[str]") -> str:
        name, default = parse_env_var(match.group(1))
        if name in variables:
            return variables[name]
        env_value = os.getenv(name)
        if env_value is not None:
            return env_value
        if default is not None:
            return default
        return match.group(0)

    return pattern.sub(replacer, path)


def expand_glob_patterns(patterns: Iterable[str], variables: Dict[str, str]) -> List[Path]:
    """Expand glob patterns (with variable support) into a de-duplicated list of file paths."""
    result: List[Path] = []
    for pattern in patterns:
        expanded = expand_path_vars(pattern, variables)
        for match in _glob.glob(expanded, recursive=True):
            path = Path(match)
            if path.is_file():
                result.append(path)
    seen: set[Path] = set()
    unique: List[Path] = []
    for path in result:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def resolve_file_path(filepath: str, base_dir: Optional[Path] = None) -> Path:
    path = Path(filepath)
    if path.is_absolute():
        return path
    return base_dir / path if base_dir else path


def is_business_template(value: str) -> bool:
    """Whether the value is a {param} business template (not one containing ${)."""
    if not value or "${" in value:
        return False
    return bool(re.search(r"\{[a-zA-Z_][a-zA-Z0-9_.]*\}", value))


# ============================================================
# Config file loading (built-in JSON / TOML, optional YAML)
# ============================================================

SUPPORTED_SUFFIXES = {".json", ".yaml", ".yml", ".toml"}


def load_config_file(filepath: Path) -> Dict[str, Any]:
    """Load a JSON / TOML / YAML config file based on its extension."""
    suffix = filepath.suffix.lower()
    if suffix == ".json":
        return _load_json(filepath)
    if suffix == ".toml":
        return _load_toml(filepath)
    if suffix in (".yaml", ".yml"):
        return _load_yaml(filepath)
    raise ConfigError(f"Unsupported config file type: {suffix} ({filepath})")


def _load_json(filepath: Path) -> Dict[str, Any]:
    with open(filepath, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_toml(filepath: Path) -> Dict[str, Any]:
    """Load TOML with the standard-library tomllib (Python >= 3.11, zero dependency)."""
    import tomllib

    with open(filepath, "rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a table: {filepath}")
    return data


def _load_yaml(filepath: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on whether the extra is installed
        raise ConfigError(
            "YAML support requires PyYAML. Install with: pip install darwin-config[yaml]"
        ) from exc
    with open(filepath, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a mapping: {filepath}")
    return data


def save_config_file(filepath: Path, data: Dict[str, Any], indent: int = 2) -> None:
    """Save config in the format selected by the file extension."""
    suffix = filepath.suffix.lower()
    if suffix == ".json":
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=indent, ensure_ascii=False)
        return
    if suffix == ".toml":
        try:
            import tomli_w  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on whether the extra is installed
            raise ConfigError(
                "TOML writing requires tomli-w. Install with: pip install darwin-config[toml]"
            ) from exc
        with open(filepath, "wb") as handle:
            tomli_w.dump(data, handle)
        return
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise ConfigError("YAML support requires PyYAML") from exc
        with open(filepath, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
        return
    raise ConfigError(f"Unsupported config file type: {suffix}")


__all__ = [
    "DEFAULT_DIRECTIVES",
    "NESTED_DIRECTIVES",
    "Directives",
    "split_directives",
    "unescape_all",
    "deep_merge",
    "get_value_by_path",
    "set_value_by_path",
    "parse_env_var",
    "expand_path_vars",
    "expand_glob_patterns",
    "resolve_file_path",
    "is_business_template",
    "load_config_file",
    "save_config_file",
    "SUPPORTED_SUFFIXES",
]
