"""L1 adapter for Flask: copy a config subtree into ``app.config``.

Usage::

    init_config(["config.yaml"])
    app = Flask(__name__)
    apply_flask_config(app)                 # uses the "flask" subtree
    apply_flask_config(app, "service")      # or a different subtree

Flask itself is not imported: any object with a dict-like ``config`` works.
"""

from typing import Any, Dict

from darwin_config.integrations._common import DataSource, resolve_data


def apply_flask_config(
    app: Any,
    path: str = "flask",
    *,
    source: DataSource = None,
    prefix: str = "",
    uppercase: bool = False,
) -> Dict[str, Any]:
    """Update ``app.config`` with a configuration subtree and return what was applied.

    Args:
        app: A Flask app (or any object whose ``config`` supports ``update``).
        path: Config path to read when ``source`` is not supplied.
        source: Explicit mapping or config path; overrides ``path``.
        prefix: Keep only keys starting with this prefix and strip it.
        uppercase: Uppercase the resulting keys (Flask config is commonly uppercase).

    Note:
        This is a one-time snapshot. Re-run after ``reload_config()`` if needed.
    """
    data = resolve_data(source, path)
    if prefix:
        data = {key[len(prefix):]: value for key, value in data.items()
                if isinstance(key, str) and key.startswith(prefix)}
    if uppercase:
        data = {str(key).upper(): value for key, value in data.items()}

    target = app.config
    if not hasattr(target, "update"):
        raise TypeError("app.config must support update()")
    target.update(data)
    return data
