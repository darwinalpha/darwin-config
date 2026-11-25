"""Node-tree tests: reads/writes, alias jumps, node-level merges, runtime expressions."""

import pytest

from darwin_config import ConfigError
from darwin_config.node import Node, dict_to_node, merge_node


# ---------- Basic reads/writes ----------


def test_node_leaf_and_branch() -> None:
    leaf = Node(1)
    assert leaf.is_leaf() and not leaf.is_branch()
    leaf.set_child("a.b", 2)
    assert leaf.is_branch()
    assert leaf.get_child("a.b").value == 2
    assert leaf.get_child("a.missing") is None
    assert leaf.get_child("").value == 1


def test_set_child_updates_existing_and_marks_unresolved() -> None:
    root = Node()
    root.set_child("a", 1, {"source": "file"})
    assert root.get_child("a").meta["source"] == "file"
    root.set_child("a", 2, {"source": "user"})
    child = root.get_child("a")
    assert child.value == 2
    assert child.meta["source"] == "user"
    assert child.meta["resolved"] is False
    assert root.get_meta("a")["source"] == "user"


def test_dict_to_node_preserves_empty_branches() -> None:
    root = dict_to_node({"a": {}, "b": {"c": 1}, "d": None})
    assert root.get_child("a").children == {}
    assert root.get_child("b.c").value == 1
    assert root.get_child("d").value is None


# ---------- Aliases ----------


def test_alias_resolution() -> None:
    root = Node()
    root.set_child("real.path", 7)
    root.set_alias("alias.path", "real.path")
    assert root.has_alias("alias.path")
    assert root.is_alias("alias.path")
    assert root.get_child_resolved("alias.path", root).value == 7
    assert root.resolve(root)["alias"]["path"] == 7


def test_circular_alias_detected() -> None:
    root = Node()
    root.set_alias("a", "b")
    root.set_alias("b", "a")
    with pytest.raises(ConfigError, match="Circular alias"):
        root.get_child_resolved("a", root)


# ---------- Node-level merges ----------


def test_merge_node_leaf_override_records_source() -> None:
    target = Node(1, {"source": "base.json"})
    merge_node(target, Node(2, {"source": "override.json"}))
    assert target.value == 2
    assert target.meta["overrides"] == ["override.json"]
    assert "timestamp" in target.meta


def test_merge_node_branch_recursive() -> None:
    target = dict_to_node({"db": {"host": "a", "port": 1}})
    source = dict_to_node({"db": {"port": 2, "user": "u"}})
    merge_node(target, source)
    assert target.resolve(target) == {"db": {"host": "a", "port": 2, "user": "u"}}


def test_merge_node_leaf_never_degrades_branch() -> None:
    target = dict_to_node({"db": {"host": "a"}})
    merge_node(target, Node("scalar", {"source": "x"}))
    assert target.resolve(target) == {"db": {"host": "a"}}


def test_merge_node_branch_replaces_leaf() -> None:
    target = Node(1)
    merge_node(target, dict_to_node({"nested": True}))
    assert target.resolve(target) == {"nested": True}


def test_merge_node_skips_alias_children() -> None:
    target = dict_to_node({"a": 1})
    source = Node()
    source.set_alias("a", "b")  # an alias on the same path must not overwrite the original value
    source.set_child("b", 2)
    merge_node(target, source)
    assert target.resolve(target) == {"a": 1, "b": 2}


# ---------- Runtime expressions ----------


def test_resolve_root_and_this(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNIT_NODE_ENV", "env-value")
    data = {
        "a": {"b": 5},
        "full_root": "${root.a.b}",
        "embedded_root": "x-${root.a.b}-y",
        "this": "${this.a.b}",
        "env": "${UNIT_NODE_ENV}",
        "env_default": "${UNIT_NODE_MISSING:fallback}",
        "calc": "%{calc: 5 * 2 }",
        "template": "{category}/{date}",
    }
    root = dict_to_node(data)
    resolved = root.resolve(root)
    assert resolved["full_root"] == 5
    assert resolved["embedded_root"] == "x-5-y"
    assert resolved["this"] == 5
    assert resolved["env"] == "env-value"
    assert resolved["env_default"] == "fallback"
    assert resolved["calc"] == 10
    assert resolved["template"] == "{category}/{date}"


def test_calc_is_sandboxed() -> None:
    root = dict_to_node({"x": "%{calc: __import__('os').getcwd()}"})
    # Invalid expressions are not evaluated; the string is returned as-is
    assert root.resolve(root)["x"] == "%{calc: __import__('os').getcwd()}"


def test_to_dict_resolved() -> None:
    root = dict_to_node({"a": 1, "ref": "${root.a}"})
    assert root.to_dict(resolved=True) == {"a": 1, "ref": 1}
