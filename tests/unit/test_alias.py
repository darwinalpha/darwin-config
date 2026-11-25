"""Unit tests for the alias module."""

import pytest

from darwin_config import ConfigMountError
from darwin_config.alias import (
    get_alias_target,
    get_aliases,
    has_alias,
    add_alias,
    resolve_path,
    set_root_node,
)
from darwin_config.node import Node, dict_to_node


def test_register_and_resolve_alias() -> None:
    root = dict_to_node({"real": {"path": 1}})
    set_root_node(root)
    add_alias("alias", "real")
    assert has_alias("alias")
    assert get_alias_target("alias") == "real"
    assert resolve_path("alias.path") == "real.path"
    assert resolve_path("alias") == "real"
    assert get_aliases() == {"alias": "real"}


def test_longest_prefix_alias() -> None:
    root = dict_to_node({"target": {"deep": {"value": 1}}})
    set_root_node(root)
    add_alias("short.cut", "target.deep")
    assert resolve_path("short.cut.value") == "target.deep.value"
    assert resolve_path("other.path") == "other.path"


def test_recursive_alias() -> None:
    root = Node()
    set_root_node(root)
    add_alias("one", "two")
    add_alias("two", "three")
    assert resolve_path("one.x") == "three.x"


def test_alias_errors() -> None:
    set_root_node(None)  # type: ignore[arg-type]
    with pytest.raises(ConfigMountError):
        add_alias("a", "b")

    root = Node()
    set_root_node(root)
    with pytest.raises(ConfigMountError, match="same as target"):
        add_alias("a", "a")
    add_alias("x", "y")
    with pytest.raises(ConfigMountError, match="already exists"):
        add_alias("x", "z")
