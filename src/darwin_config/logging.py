"""
Logging helpers.

Built on the standard-library logging module; zero external dependencies.
"""

import logging
from typing import Any

_LOGGER_CACHE: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (cached)."""
    if name not in _LOGGER_CACHE:
        _LOGGER_CACHE[name] = logging.getLogger(name)
    return _LOGGER_CACHE[name]


def configure(level: int | str = logging.WARNING, **kwargs: Any) -> None:
    """Optional: configure the root logger. If not called, the host app's logging config applies."""
    logging.basicConfig(level=level, **kwargs)


__all__ = ["get_logger", "configure"]
