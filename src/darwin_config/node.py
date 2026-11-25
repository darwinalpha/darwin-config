"""
Node tree: in-memory representation of configuration and runtime expression evaluation.

Node shape is determined by children:
    - None        leaf node, value holds the actual value
    - {}          empty branch node
    - {key: Node} branch node

Runtime expressions:
    ${root.xxx}  global config-tree reference
    ${this.xxx}  in-file reference (resolved at load time; leftovers fall back to a root-relative lookup)
    ${VAR}       environment variable / ${VAR:default}
    %{calc: ...} restricted arithmetic expression (must be quoted in YAML)
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, Set

from darwin_config.exceptions import ConfigError


class Node:
    """A configuration node."""

    __slots__ = ("value", "meta", "children")

    def __init__(self, value: Any = None, meta: Optional[Dict[str, Any]] = None):
        self.value = value
        self.meta = dict(meta or {})
        self.children: Optional[Dict[str, "Node"]] = None

    # ---------- Basic queries ----------

    def is_leaf(self) -> bool:
        return self.children is None

    def is_branch(self) -> bool:
        return self.children is not None

    def get_child(self, path: str) -> Optional["Node"]:
        if not path:
            return self
        if self.children is None:
            return None
        node: Node = self
        for key in path.split("."):
            if node.children is None or key not in node.children:
                return None
            node = node.children[key]
        return node

    def get_child_resolved(
        self,
        path: str,
        root_node: Optional["Node"] = None,
        visited: Optional[Set[str]] = None,
    ) -> Optional["Node"]:
        """Look up a node, resolving aliases recursively and detecting cycles."""
        if root_node is None:
            root_node = self
        if visited is None:
            visited = set()
        if not path:
            return self
        if path in visited:
            raise ConfigError(f"Circular alias reference: {path}")
        visited.add(path)

        node = self.get_child(path)
        if node is None:
            return None
        if node.meta.get("is_alias", False) and isinstance(node.value, str):
            return root_node.get_child_resolved(node.value, root_node, visited)
        return node

    # ---------- Writes ----------

    def set_child(self, path: str, value: Any, meta: Optional[Dict[str, Any]] = None) -> None:
        if not path:
            self.value = value
            if meta:
                self.meta.update(meta)
            return
        node: Node = self
        for key in path.split(".")[:-1]:
            if node.children is None:
                node.children = {}
            if key not in node.children:
                node.children[key] = Node()
            node = node.children[key]
        if node.children is None:
            node.children = {}
        last = path.split(".")[-1]
        if last in node.children:
            child = node.children[last]
            child.value = value
            if meta:
                child.meta.update(meta)
            child.meta["resolved"] = False
        else:
            node.children[last] = Node(value=value, meta=meta)

    def set_alias(self, alias_path: str, target_path: str) -> None:
        node: Node = self
        for key in alias_path.split(".")[:-1]:
            if node.children is None:
                node.children = {}
            if key not in node.children:
                node.children[key] = Node()
            node = node.children[key]
        if node.children is None:
            node.children = {}
        node.children[alias_path.split(".")[-1]] = Node(
            value=target_path,
            meta={"is_alias": True, "resolved": True, "source": "alias"},
        )

    def has_alias(self, path: str) -> bool:
        node = self.get_child(path)
        return node is not None and node.meta.get("is_alias", False)

    def get_value(self, path: str = "") -> Any:
        if not path:
            return self.value
        node = self.get_child(path)
        return node.value if node else None

    def get_meta(self, path: str = "") -> Dict[str, Any]:
        if not path:
            return self.meta
        node = self.get_child(path)
        return node.meta if node else {}

    def is_alias(self, path: str = "") -> bool:
        if not path:
            return self.meta.get("is_alias", False)
        node = self.get_child(path)
        return node is not None and node.meta.get("is_alias", False)

    # ---------- Evaluation / conversion ----------

    def resolve(self, root_node: Optional["Node"] = None) -> Any:
        """Evaluate recursively: follow aliases, turn branches into dicts, resolve leaf expressions and cache."""
        if root_node is None:
            root_node = self

        if self.meta.get("is_alias", False):
            target = self.value
            if isinstance(target, str):
                target_node = root_node.get_child_resolved(target, root_node)
                if target_node:
                    return target_node.resolve(root_node)
            return self.value

        if self.children is not None:
            return {key: child.resolve(root_node) for key, child in self.children.items()}

        if self.meta.get("resolved", False):
            return self.value

        if isinstance(self.value, str):
            resolved_value = _resolve_string(self.value, root_node)
            self.value = resolved_value
            self.meta["resolved"] = True
            return resolved_value

        self.meta["resolved"] = True
        return self.value

    def to_dict(self, resolved: bool = False, root_node: Optional["Node"] = None) -> Any:
        if root_node is None:
            root_node = self
        if resolved:
            return self.resolve(root_node)

        if self.children is not None:
            result: Dict[str, Any] = {}
            for key, child in self.children.items():
                if child.meta.get("is_alias", False):
                    if isinstance(child.value, str):
                        target_node = root_node.get_child_resolved(child.value, root_node)
                        if target_node:
                            result[key] = target_node.to_dict(False, root_node)
                    continue
                child_result = child.to_dict(False, root_node)
                if child_result is None and child.children is not None:
                    result[key] = {}
                elif child_result is not None:
                    result[key] = child_result
            return result
        return self.value

    def __repr__(self) -> str:
        keys = list(self.children.keys()) if self.children is not None else None
        kind = "AliasNode" if self.meta.get("is_alias") else "Node"
        if self.children is not None:
            return f"{kind}(children={keys})"
        return f"{kind}(value={self.value!r}, meta={self.meta})"


def dict_to_node(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> Node:
    """Convert a dict into a node tree; an empty dict maps to an empty branch node."""
    root = Node(meta=meta or {})
    root.children = {}
    for key, value in data.items():
        if isinstance(value, dict):
            child = dict_to_node(value, meta)
            if child.children is not None or child.value is not None:
                root.children[key] = child
        else:
            root.children[key] = Node(value=value, meta=dict(meta or {}))
    return root


def merge_node(target: Node, source: Node, path: str = "") -> None:
    """Deep-merge two node trees."""
    if source.meta.get("is_alias", False):
        return

    if target.children is None and source.children is None:
        source_meta = source.meta.get("source", "unknown")
        target.meta.setdefault("overrides", []).append(source_meta)
        target.meta["timestamp"] = datetime.now().isoformat()
        target.value = source.value
        target.meta.update(source.meta)
        target.meta["resolved"] = False
        return

    if target.children is None and source.children is not None:
        target.value = None
        target.children = source.children
        target.meta.update(source.meta)
        target.meta["resolved"] = True
        return

    # A branch must not degrade into a leaf
    if target.children is not None and source.children is None:
        return

    if target.children is not None and source.children is not None:
        for key, child in source.children.items():
            if child.meta.get("is_alias", False):
                continue
            if key in target.children:
                merge_node(target.children[key], child, f"{path}.{key}" if path else key)
            else:
                target.children[key] = child


# ============================================================
# Runtime expressions
# ============================================================

_ROOT_RE = re.compile(r"\$\{root\.([^}]+)\}")
_THIS_RE = re.compile(r"\$\{this\.([^}]+)\}")
_ENV_RE = re.compile(r"\$\{([^}]+)\}")
_CALC_RE = re.compile(r"%\{calc:\s*([^}]*)\}")

_ALLOWED_NAMES = {
    "True": True,
    "False": False,
    "None": None,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sum": sum,
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
}


def _resolve_string(value: str, root_node: Node) -> Any:
    """Resolve expressions inside a string (whole-string references may return non-string values)."""
    if "${" not in value and "%{" not in value:
        return value

    # Whole string ${root.xxx}
    match = _ROOT_RE.fullmatch(value)
    if match:
        resolved = _resolve_root_path(match.group(1), root_node)
        return resolved if resolved is not None else value

    # Whole string ${this.xxx}
    match = _THIS_RE.fullmatch(value)
    if match:
        resolved = _resolve_root_path(match.group(1), root_node)
        return resolved if resolved is not None else value

    # Whole string ${VAR} / ${VAR:default}
    match = _ENV_RE.fullmatch(value)
    if match and not match.group(1).startswith(("root.", "this.")):
        resolved = _resolve_env_var(match.group(1))
        return resolved if resolved is not None else value

    # Whole string %{calc: ...}
    match = _CALC_RE.fullmatch(value)
    if match:
        resolved = _resolve_calc(match.group(1).strip(), root_node)
        return resolved if resolved is not None else value

    # Mixed string: root -> this -> env -> calc
    result = value
    for pattern, resolver in (
        (_ROOT_RE, lambda expr: _resolve_root_path(expr, root_node)),
        (_THIS_RE, lambda expr: _resolve_root_path(expr, root_node)),
        (_CALC_RE, lambda expr: _resolve_calc(expr.strip(), root_node)),
    ):
        result = pattern.sub(lambda m: _sub_resolver(m, resolver), result)

    def env_sub(match: "re.Match[str]") -> str:
        expr = match.group(1)
        if expr.startswith(("root.", "this.")):
            return match.group(0)
        resolved = _resolve_env_var(expr)
        return match.group(0) if resolved is None else str(resolved)

    result = _ENV_RE.sub(env_sub, result)
    return result


def _sub_resolver(match: "re.Match[str]", resolver: Any) -> str:
    resolved = resolver(match.group(1))
    return match.group(0) if resolved is None else str(resolved)


def _resolve_root_path(path: str, root_node: Node) -> Optional[Any]:
    node = root_node.get_child_resolved(path, root_node)
    return node.resolve(root_node) if node else None


def _resolve_env_var(expr: str) -> Optional[str]:
    from darwin_config.utils import parse_env_var

    name, default = parse_env_var(expr)
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value
    return default


def _resolve_calc(expr: str, root_node: Node) -> Optional[Any]:
    resolved_expr = _resolve_string(expr, root_node)
    if not isinstance(resolved_expr, str):
        return resolved_expr
    try:
        # nosec: builtins are cleared and only whitelisted functions are exposed, for internal config calculations
        return eval(resolved_expr, {"__builtins__": {}}, _ALLOWED_NAMES)  # noqa: S307
    except Exception:
        return None


__all__ = ["Node", "dict_to_node", "merge_node"]
