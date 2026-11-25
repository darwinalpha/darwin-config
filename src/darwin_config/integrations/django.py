"""L1 adapter for Django settings: expose only uppercase names.

In ``settings.py``::

    from darwin_config import init_config
    from darwin_config.integrations.django import django_settings

    init_config(["config.yaml"])
    globals().update(django_settings())              # reads the "django" subtree

Django ignores module-level names that are not uppercase, so by default only
uppercase keys are returned. Pass ``uppercase=True`` to uppercase every key.

Django itself is not imported: the adapter returns a plain dict, which can be
merged into any namespace (a module, a dict, etc.).
"""

from collections.abc import Mapping
from typing import Any, Dict

from darwin_config.integrations._common import DataSource, resolve_data


def django_settings(
    path: str = "django",
    *,
    source: DataSource = None,
    uppercase: bool = False,
) -> Dict[str, Any]:
    """Return the config subtree as a dict of Django-compatible setting names.

    Args:
        path: Config path to read when ``source`` is not supplied.
        source: Explicit mapping or config path; overrides ``path``.
        uppercase: Uppercase all keys instead of filtering to already-uppercase ones.
    """
    data = resolve_data(source, path)
    if uppercase:
        return {str(key).upper(): value for key, value in data.items()}
    return {
        key: value
        for key, value in data.items()
        if isinstance(key, str) and key.isupper()
    }


def apply_django_settings(
    namespace: Any = None,
    path: str = "django",
    *,
    source: DataSource = None,
    uppercase: bool = False,
) -> Dict[str, Any]:
    """Merge compatible settings into ``namespace`` and return what was applied.

    ``namespace`` may be a module (its ``__dict__`` is updated), a plain dict,
    or ``None`` — in the latter case nothing is mutated and the caller can
    do ``globals().update(...)`` itself.
    """
    settings = django_settings(path, source=source, uppercase=uppercase)
    if namespace is not None:
        target = vars(namespace) if not isinstance(namespace, Mapping) else namespace
        if not hasattr(target, "update"):
            raise TypeError("namespace must be a module, a dict, or None")
        target.update(settings)
    return settings
