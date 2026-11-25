"""
Optional L1 (data-adaptation) integrations for popular frameworks.

Import the adapter you need explicitly so that importing this package never
pulls in a third-party framework::

    from darwin_config.integrations.flask import apply_flask_config
    from darwin_config.integrations.django import apply_django_settings, django_settings
    from darwin_config.integrations.pydantic import validate_with_pydantic

Flask and Django adapters are duck-typed and need no framework import.
The Pydantic adapter imports ``pydantic`` lazily and requires the extra::

    pip install darwin-config[pydantic]

These adapters copy a configuration snapshot into the framework. Runtime
changes made with ``set_config`` / ``add_config`` do not propagate
automatically; re-run the adapter after a reload when needed.
"""

__all__: list[str] = []
