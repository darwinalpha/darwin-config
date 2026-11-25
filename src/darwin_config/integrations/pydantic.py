"""L1 adapter for Pydantic: validate a config subtree into a typed model.

Usage::

    init_config(["config.yaml"])
    settings = validate_with_pydantic(Settings, "app")   # Settings is a BaseModel

Requires the optional dependency::

    pip install darwin-config[pydantic]

The import is lazy, so the core package and the other adapters remain
dependency-free.
"""

from typing import Any, Type, TypeVar

from darwin_config.integrations._common import DataSource, resolve_data

T = TypeVar("T")


def validate_with_pydantic(
    model: Type[T],
    path: str = "",
    *,
    source: DataSource = None,
    strict: bool = False,
    **kwargs: Any,
) -> T:
    """Validate a config mapping with ``pydantic.TypeAdapter`` and return a model instance.

    Args:
        model: A Pydantic model class (or any type accepted by ``TypeAdapter``).
        path: Config path to read when ``source`` is not supplied; empty means the whole tree.
        source: Explicit mapping or config path; overrides ``path``.
        strict: Passed through to ``TypeAdapter.validate_python``.
        **kwargs: Additional keyword arguments for ``validate_python``.

    Raises:
        ImportError: If ``pydantic`` is not installed.
    """
    try:
        from pydantic import TypeAdapter
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "pydantic is required for darwin_config.integrations.pydantic; "
            "install it with: pip install darwin-config[pydantic]"
        ) from exc

    data = resolve_data(source, path)
    return TypeAdapter(model).validate_python(data, strict=strict, **kwargs)
