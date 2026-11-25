"""Shared helpers for the L1 framework adapters."""

from collections.abc import Mapping
from typing import Any, Dict, Optional, Union

from darwin_config import get_config

DataSource = Optional[Union[str, Mapping[str, Any]]]


def resolve_data(source: DataSource = None, path: str = "") -> Dict[str, Any]:
    """Return a plain dict either from an explicit mapping or from a config path.

    ``source`` wins over ``path`` when both are given. An empty result is
    represented by ``{}`` so adapters can always call ``.items()``.
    """
    if isinstance(source, Mapping):
        data: Any = dict(source)
    else:
        data = get_config(source if isinstance(source, str) else path)
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise TypeError(f"Configuration at {source or path!r} is not a mapping")
    return dict(data)
