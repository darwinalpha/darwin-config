"""
File-level directive processors.

Directives (remappable via Directives):
    import  : import other configs (file level, loaded immediately)
    schema  : validation rules (file level, validated immediately)
    merge   : merge other objects in the same file (processed at the end of the file level)
    this    : in-file reference ${this.xxx} (replaced recursively at the end)

Processing order: import -> schema -> merge -> this
Environment variable substitution runs after schema in the substitute module.
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional, Set

from darwin_config.exceptions import (
    ConfigCircularReferenceError,
    ConfigError,
    ConfigValidationError,
)
from darwin_config.logging import get_logger
from darwin_config.schema import Schema
from darwin_config.utils import (
    Directives,
    deep_merge,
    expand_path_vars,
    get_value_by_path,
    load_config_file,
    split_directives,
)

logger = get_logger(__name__)
_MAX_DEPTH = 20
_THIS_RE = re.compile(r"\$\{this\.([^}]+)\}")


# ============================================================
# import
# ============================================================


def process_file_import(
    config: Dict[str, Any],
    current_dir: Path,
    variables: Optional[Dict[str, str]] = None,
    mount: str = "",
    directives: Optional[Directives] = None,
    _depth: int = 0,
) -> Dict[str, Any]:
    """Process the import directive recursively (including nested objects)."""
    if _depth > _MAX_DEPTH:
        raise ConfigCircularReferenceError("Too many import levels (possible circular reference)")
    directives = directives or Directives()
    variables = variables or {}

    business, found = split_directives(config, directives, {"import"})
    import_items = found.get("import")

    result = business
    if import_items:
        paths = [import_items] if isinstance(import_items, str) else import_items
        if not isinstance(paths, list):
            raise ConfigError(f"import must be string or list, got {type(import_items)}")
        merged: Dict[str, Any] = {}
        for import_path in paths:
            if not isinstance(import_path, str):
                raise ConfigError(f"import path must be string, got {type(import_path)}")
            expanded = expand_path_vars(import_path, variables)
            full_path = current_dir / expanded
            if not full_path.exists():
                logger.warning("Import file not found: %s", full_path)
                continue
            try:
                imported = load_config_file(full_path)
                imported = process_file_import(
                    imported, full_path.parent, variables, mount, directives, _depth + 1
                )
                merged = deep_merge(merged, imported)
                logger.debug("Loaded: %s", full_path)
            except ConfigCircularReferenceError:
                raise
            except ConfigError as exc:
                logger.warning("Failed to import %s: %s", full_path, exc)
        result = deep_merge(merged, business)

    return _process_nested_import(result, current_dir, variables, mount, directives, _depth + 1)


def _process_nested_import(
    config: Dict[str, Any],
    current_dir: Path,
    variables: Dict[str, str],
    mount: str,
    directives: Directives,
    _depth: int,
) -> Dict[str, Any]:
    """Process imports in nested objects recursively."""
    if _depth > _MAX_DEPTH:
        raise ConfigCircularReferenceError("Too many import levels (possible circular reference)")
    result: Dict[str, Any] = {}
    for key, value in config.items():
        nested_business, nested_found = (
            split_directives(value, directives, {"import"}) if isinstance(value, dict) else ({}, {})
        )
        if isinstance(value, dict) and "import" in nested_found:
            result[key] = process_file_import(
                value, current_dir, variables, mount, directives, _depth + 1
            )
        elif isinstance(value, dict):
            result[key] = _process_nested_import(value, current_dir, variables, mount, directives, _depth + 1)
        elif isinstance(value, list):
            result[key] = [
                _process_nested_import(item, current_dir, variables, mount, directives, _depth + 1)
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


# ============================================================
# schema
# ============================================================


def process_file_schema(
    config: Dict[str, Any],
    validate: bool = True,
    base_dir: Optional[Path] = None,
    directives: Optional[Directives] = None,
    top_level: bool = True,
) -> Dict[str, Any]:
    """Process the schema directive: validate and fill defaults."""
    directives = directives or Directives()
    business, found = split_directives(config, directives, {"schema"})
    if not validate:
        return business

    schema_source = found.get("schema")
    if schema_source is None:
        return business

    try:
        schema = Schema.load(schema_source, base_dir)
        return schema.validate_and_fill(business)
    except ConfigValidationError:
        raise


# ============================================================
# merge
# ============================================================


def _process_merge_at_level(
    config: Dict[str, Any],
    root_config: Dict[str, Any],
    directives: Directives,
    _depth: int,
) -> Dict[str, Any]:
    if _depth > _MAX_DEPTH:
        raise ConfigCircularReferenceError("Too many merge iterations (possible circular reference)")

    business, found = split_directives(config, directives, {"merge"})
    merge_sources = found.get("merge")
    if merge_sources is None:
        return config

    sources = [merge_sources] if isinstance(merge_sources, str) else merge_sources
    if not isinstance(sources, list):
        logger.warning("merge must be string or list, got %s", type(merge_sources))
        return config

    merged: Dict[str, Any] = {}
    for expr in sources:
        if not isinstance(expr, str):
            logger.warning("merge source must be string, got %s", type(expr))
            continue
        clean = expr.strip()
        if clean.startswith("${") and clean.endswith("}"):
            clean = clean[2:-1]
        if not clean.startswith("this."):
            logger.warning("merge source must be a this reference, got: %s", expr)
            continue
        try:
            source_value = get_value_by_path(root_config, clean[5:])
            if isinstance(source_value, dict) and directives.key_for("merge") in source_value:
                source_value = _process_merge_at_level(
                    source_value, root_config, directives, _depth + 1
                )
            if isinstance(source_value, dict):
                merged = deep_merge(merged, source_value)
            else:
                logger.warning("merge source '%s' is not a dict, got %s", expr, type(source_value).__name__)
        except KeyError as exc:
            logger.warning("merge source '%s' not found: %s", expr, exc)

    return deep_merge(merged, business)


def process_file_merge(
    config: Dict[str, Any],
    root_config: Optional[Dict[str, Any]] = None,
    directives: Optional[Directives] = None,
    _depth: int = 0,
) -> Dict[str, Any]:
    """Process merge directives in all nested objects recursively."""
    if _depth > _MAX_DEPTH:
        raise ConfigCircularReferenceError("Too many merge iterations (possible circular reference)")
    directives = directives or Directives()
    if root_config is None:
        root_config = config

    _, found = split_directives(config, directives, {"merge"})
    if "merge" in found:
        config = _process_merge_at_level(config, root_config, directives, _depth + 1)

    result: Dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = process_file_merge(value, root_config, directives, _depth + 1)
        elif isinstance(value, list):
            result[key] = [
                process_file_merge(item, root_config, directives, _depth + 1)
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


# ============================================================
# this references
# ============================================================


def process_file_this_refs(
    config: Dict[str, Any],
    _depth: int = 0,
    _visited: Optional[Set[int]] = None,
    _root_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Replace in-file ${this.xxx} references recursively."""
    if _depth > _MAX_DEPTH:
        raise ConfigCircularReferenceError("Too many this reference iterations")
    if _visited is None:
        _visited = set()
    if _root_config is None:
        _root_config = config
    return _replace_this_refs(config, _root_config, _depth + 1, _visited)


def _replace_this_refs(
    value: Any,
    root_config: Dict[str, Any],
    _depth: int,
    _visited: Set[int],
) -> Any:
    if _depth > _MAX_DEPTH:
        raise ConfigCircularReferenceError("Too many this reference iterations")

    if isinstance(value, str):
        if "${this." not in value:
            return value
        full = _THIS_RE.fullmatch(value)
        if full:
            path = full.group(1)
            try:
                resolved = get_value_by_path(root_config, path)
            except KeyError as exc:
                raise ConfigError(f"This path '{path}' not found") from exc
            if isinstance(resolved, (dict, str)):
                return _replace_this_refs(resolved, root_config, _depth + 1, _visited)
            return resolved

        result = value
        for match in _THIS_RE.finditer(result):
            path = match.group(1)
            try:
                resolved = get_value_by_path(root_config, path)
            except KeyError as exc:
                raise ConfigError(f"This path '{path}' not found") from exc
            result = result.replace(match.group(0), str(resolved))
        if "${this." in result:
            return _replace_this_refs(result, root_config, _depth + 1, _visited)
        return result

    if isinstance(value, dict):
        object_id = id(value)
        if object_id in _visited:
            raise ConfigCircularReferenceError("Circular reference detected in this references")
        _visited.add(object_id)
        result_dict = {k: _replace_this_refs(v, root_config, _depth + 1, _visited) for k, v in value.items()}
        _visited.remove(object_id)
        return result_dict

    if isinstance(value, list):
        return [_replace_this_refs(item, root_config, _depth + 1, _visited) for item in value]

    return value


__all__ = [
    "process_file_import",
    "process_file_schema",
    "process_file_merge",
    "process_file_this_refs",
]
