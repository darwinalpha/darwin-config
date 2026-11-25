"""
Alias management: an alias is a special node in the tree (is_alias=True, value is the target path).
"""

from typing import Dict, Optional

from darwin_config.exceptions import ConfigMountError
from darwin_config.logging import get_logger
from darwin_config.node import Node

_root_node: Optional[Node] = None


def _get_logger():
    return get_logger(__name__)


def set_root_node(node: Node) -> None:
    global _root_node
    _root_node = node


def add_alias(alias: str, target: str) -> None:
    """Register an alias: alias and target read and write the same node.

    The target path need not exist yet; it is resolved on read (same as the lazy
    resolution of ${root.xxx}).
    """
    if _root_node is None:
        raise ConfigMountError("Root node is not initialized")
    if alias == target:
        raise ConfigMountError(f"Alias cannot be the same as target: {alias}")
    if _root_node.has_alias(alias):
        raise ConfigMountError(f"Alias '{alias}' already exists")
    _get_logger().debug("Register alias: %s -> %s", alias, target)
    _root_node.set_alias(alias, target)


def resolve_path(path: str) -> str:
    """Resolve aliases in a path (whole string + longest prefix, recursively)."""
    if _root_node is None:
        return path
    if _root_node.is_alias(path):
        node = _root_node.get_child(path)
        if node and isinstance(node.value, str):
            return resolve_path(node.value)

    parts = path.split(".")
    for index in range(len(parts), 0, -1):
        prefix = ".".join(parts[:index])
        if _root_node.is_alias(prefix):
            node = _root_node.get_child(prefix)
            if node and isinstance(node.value, str):
                remaining = ".".join(parts[index:])
                resolved = resolve_path(node.value)
                return f"{resolved}.{remaining}" if remaining else resolved
    return path


def has_alias(path: str) -> bool:
    return _root_node is not None and _root_node.has_alias(path)


def get_aliases() -> Dict[str, str]:
    result: Dict[str, str] = {}
    if _root_node is None:
        return result

    def traverse(node: Node, current: str = "") -> None:
        if node.meta.get("is_alias", False) and isinstance(node.value, str):
            result[current] = node.value
        if node.children is not None:
            for key, child in node.children.items():
                traverse(child, f"{current}.{key}" if current else key)

    traverse(_root_node)
    return result


def get_alias_target(alias: str) -> Optional[str]:
    if _root_node is None:
        return None
    node = _root_node.get_child(alias)
    if node is None or not node.meta.get("is_alias", False):
        return None
    return node.value if isinstance(node.value, str) else None


__all__ = [
    "set_root_node",
    "add_alias",
    "resolve_path",
    "has_alias",
    "get_aliases",
    "get_alias_target",
]
