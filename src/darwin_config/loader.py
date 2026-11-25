"""
Configuration loader core and global public API.

Syntax:
    - directives: import / merge / mount / schema (bare keywords, remappable)
    - references: ${this.xxx} (in-file), ${root.xxx} (global)
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from darwin_config.alias import add_alias, resolve_path, set_root_node
from darwin_config.exceptions import ConfigError, ConfigPathNotFoundError
from darwin_config.logging import get_logger
from darwin_config.node import Node, dict_to_node, merge_node
from darwin_config.processor import (
    process_file_import,
    process_file_merge,
    process_file_schema,
    process_file_this_refs,
)
from darwin_config.substitute import replace_env_vars
from darwin_config.utils import (
    Directives,
    expand_glob_patterns,
    load_config_file,
    split_directives,
    unescape_all,
)

logger = get_logger(__name__)


# ============================================================
# Global state
# ============================================================

_root_node: Node = Node()
_initialized: bool = False
_mount_point: str = ""
_business_values: Dict[str, str] = {}
_validate_on_load: bool = False
_base_dir: Optional[Path] = None
_add_config_calls: List[Dict[str, Any]] = []
_config_files: List[str] = []
_directives: Directives = Directives()


def _mount_node(root: Node, mount_path: str, node: Node) -> None:
    if not mount_path:
        merge_node(root, node)
        return
    current = root
    parts = mount_path.split(".")
    for part in parts[:-1]:
        if current.children is None:
            current.children = {}
        if part not in current.children:
            current.children[part] = Node()
        current = current.children[part]
    if current.children is None:
        current.children = {}
    last = parts[-1]
    if last in current.children:
        merge_node(current.children[last], node)
    else:
        current.children[last] = node


# ============================================================
# ConfigLoader class
# ============================================================


class ConfigLoader:
    """A standalone configuration loader."""

    def __init__(
        self,
        config_files: List[str],
        mount: str = "",
        variables: Optional[Dict[str, str]] = None,
        validate: bool = False,
        base_dir: Optional[Path] = None,
        directives: Optional[Directives] = None,
    ):
        self.config_files = config_files
        self.mount = mount
        self.variables = variables or {}
        self.validate = validate
        self.base_dir = base_dir or Path.cwd()
        self.directives = directives or Directives()

    def load(self) -> Dict[str, Any]:
        """Load all configuration files and return the merged dict."""
        file_paths = expand_glob_patterns(self.config_files, self.variables)
        if not file_paths:
            logger.warning("No config files found: %s", self.config_files)
            return {self.mount: {}} if self.mount else {}

        processed = [self.process_file(path) for path in file_paths]
        final_config: Dict[str, Any] = {}
        for config in processed:
            final_config = _deep_merge_dicts(final_config, config)
        return {self.mount: final_config} if self.mount else final_config

    def process_file(self, filepath: Path) -> Dict[str, Any]:
        """Process one file: load -> import -> schema -> env -> merge -> this."""
        config = load_config_file(filepath)
        return self.process_config(config, filepath.parent, source=str(filepath))

    def process_config(self, config: Dict[str, Any], base_dir: Path, source: str = "memory") -> Dict[str, Any]:
        """Run the full pipeline on a config dict (reused by add_config)."""
        directives = self.directives

        # 1. import
        config = process_file_import(config, base_dir, self.variables, self.mount, directives)

        # 2. mount / schema (top-level directives)
        config, top_directives = split_directives(config, directives, {"mount", "schema"})
        schema_source = top_directives.get("schema")

        # 3. schema validation + default filling
        if self.validate and schema_source is not None:
            from darwin_config.schema import Schema

            config = Schema.load(schema_source, base_dir).validate_and_fill(config)

        # 4. environment variable substitution
        config = replace_env_vars(config, self.variables)

        # 5. merge
        config = process_file_merge(config, directives=directives)

        # 6. this references
        config = process_file_this_refs(config)

        # 7. unescape all ~ prefixed keys at the end of the pipeline
        return unescape_all(config, directives)

    @property
    def actual_mount(self) -> str:
        return self.mount


def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    from darwin_config.utils import deep_merge

    return deep_merge(base, override)


# ============================================================
# Public API
# ============================================================


def init_config(
    files: List[str],
    mount: str = "",
    values: Optional[Dict[str, str]] = None,
    validate: bool = False,
    base_dir: Optional[Path] = None,
    directives: Optional[Dict[str, str]] = None,
) -> None:
    """Initialize the configuration system."""
    global _root_node, _initialized, _mount_point, _business_values
    global _validate_on_load, _base_dir, _config_files, _add_config_calls, _directives

    _mount_point = mount
    _business_values = values or {}
    _config_files = files
    _initialized = True
    _validate_on_load = validate
    _base_dir = base_dir or Path.cwd()
    _add_config_calls = []
    _directives = Directives(directives)

    _root_node = Node()
    set_root_node(_root_node)

    loader = ConfigLoader(
        config_files=files,
        mount=mount,
        variables=_business_values,
        validate=validate,
        base_dir=_base_dir,
        directives=_directives,
    )
    result = loader.load()
    source = str(files[0]) if files else "unknown"

    if mount:
        config_data = result.get(mount) or {}
        node = dict_to_node(config_data, meta={"source": source, "mount": mount})
        _mount_node(_root_node, mount, node)
    else:
        node = dict_to_node(result, meta={"source": source, "mount": ""})
        _root_node.children = node.children


def add_config(
    source: Union[str, Path, Dict[str, Any]],
    mount: Optional[str] = None,
    values: Optional[Dict[str, str]] = None,
    validate: bool = True,
) -> None:
    """Append configuration (from a file or a dict)."""
    global _root_node, _add_config_calls

    if not _initialized:
        raise RuntimeError("Please call init_config() to initialize the configuration system first")

    _add_config_calls.append(
        {"source": source, "mount": mount, "values": values, "validate": validate}
    )
    merged_values = {**_business_values, **(values or {})}

    loader = ConfigLoader(
        config_files=[],
        variables=merged_values,
        validate=validate if validate is not None else _validate_on_load,
        base_dir=_base_dir or Path.cwd(),
        directives=_directives,
    )

    if isinstance(source, (str, Path)):
        filepath = Path(source)
        if not filepath.exists():
            raise ConfigError(f"Config file not found: {filepath}")
        raw = load_config_file(filepath)
        _, top = split_directives(raw, _directives, {"mount"})
        final_mount = top.get("mount", "")
        if mount is not None and mount != final_mount:
            add_alias(mount, final_mount)
        processed = loader.process_config(raw, filepath.parent, source=str(filepath))
        meta = {"source": str(filepath), "mount": final_mount}
    else:
        raw = source
        _, top = split_directives(raw, _directives, {"mount"})
        final_mount = top.get("mount", "")
        if mount is not None and mount != final_mount:
            add_alias(mount, final_mount)
        processed = loader.process_config(raw, _base_dir or Path.cwd(), source="memory")
        meta = {"source": "memory", "mount": final_mount}

    _mount_node(_root_node, final_mount, dict_to_node(processed, meta=meta))


def _require_initialized() -> None:
    if not _initialized:
        raise RuntimeError("Please call init_config() to initialize the configuration system first")


def get_config(path: str = "", default: Any = None, raise_on_not_found: bool = False) -> Any:
    """Read a configuration value."""
    _require_initialized()
    if not path:
        return _root_node.to_dict(resolved=True)
    actual_path = resolve_path(path)
    node = _root_node.get_child_resolved(actual_path, _root_node)
    if node is None:
        if raise_on_not_found:
            raise ConfigPathNotFoundError(f"Path not found: {path}")
        return default
    return node.resolve(_root_node)


def try_config(*paths: str, default: Any = None) -> Any:
    """Try paths in order and return the first non-None value."""
    for path in paths:
        try:
            value = get_config(path)
            if value is not None:
                return value
        except (ConfigError, KeyError, RuntimeError):
            continue
    return default


def set_config(path: str, value: Any) -> None:
    """Set a configuration value at runtime."""
    _require_initialized()
    actual_path = resolve_path(path)
    _root_node.set_child(
        actual_path,
        value,
        meta={"source": "user", "timestamp": datetime.now().isoformat(), "resolved": False},
    )


def get_meta(path: str) -> Dict[str, Any]:
    _require_initialized()
    return _root_node.get_meta(resolve_path(path))


def reload_config() -> Dict[str, Any]:
    """Reload configuration and replay all add_config calls."""
    _require_initialized()
    global _root_node, _add_config_calls

    calls = _add_config_calls.copy()
    _root_node = Node()
    set_root_node(_root_node)

    loader = ConfigLoader(
        config_files=_config_files,
        mount=_mount_point,
        variables=_business_values,
        validate=_validate_on_load,
        base_dir=_base_dir or Path.cwd(),
        directives=_directives,
    )
    result = loader.load()
    source = str(_config_files[0]) if _config_files else "unknown"

    if _mount_point:
        config_data = result.get(_mount_point) or {}
        node = dict_to_node(config_data, meta={"source": source, "mount": _mount_point})
        _mount_node(_root_node, _mount_point, node)
    else:
        node = dict_to_node(result, meta={"source": source, "mount": ""})
        _root_node.children = node.children

    _add_config_calls = []
    for call in calls:
        add_config(**call)
    return get_config()


def config_trace(path: str) -> str:
    """Return a human-readable source-trace string for a config path."""
    if not _initialized:
        return "Configuration system is not initialized"
    meta = get_meta(resolve_path(path))
    if not meta:
        return f"Path '{path}' not found"
    source = meta.get("source", "unknown")
    mount = meta.get("mount", "")
    overrides = meta.get("overrides", [])
    result = f"{path} → {source}"
    if mount:
        result += f" (mount: {mount})"
    if overrides:
        result += f" (overridden by: {', '.join(overrides)})"
    return result


def get_trace_summary() -> Dict[str, int]:
    """Count configuration items grouped by source."""
    summary: Dict[str, int] = {}

    def traverse(node: Node) -> None:
        if node.meta.get("is_alias"):
            return
        source = node.meta.get("source")
        if source:
            summary[source] = summary.get(source, 0) + 1
        if node.children:
            for child in node.children.values():
                traverse(child)

    traverse(_root_node)
    return summary


__all__ = [
    "ConfigLoader",
    "init_config",
    "add_config",
    "get_config",
    "try_config",
    "set_config",
    "get_meta",
    "reload_config",
    "config_trace",
    "get_trace_summary",
]
