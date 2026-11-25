"""
darwin-config exception hierarchy.

All exceptions are defined internally and depend on no external packages.
"""

from typing import Any, Dict, Optional


class ConfigError(Exception):
    """Base class for configuration errors."""


class ConfigNotFoundError(ConfigError):
    """Configuration not found."""


class ConfigValidationError(ConfigError):
    """Validation failure, carrying a dict of field-level errors."""

    def __init__(self, message: str, errors: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.errors = errors or {}

    def __str__(self) -> str:
        if self.errors:
            details = "\n".join(
                f"  {path}: {', '.join(messages)}" for path, messages in self.errors.items()
            )
            return f"{super().__str__()}\n{details}"
        return super().__str__()


class ConfigCircularReferenceError(ConfigError):
    """Circular reference error."""


class ConfigPathNotFoundError(ConfigError):
    """Configuration path does not exist."""


class ConfigEnvVarError(ConfigError):
    """Missing environment variable."""


class ConfigMountError(ConfigError):
    """Mount or alias error."""


__all__ = [
    "ConfigError",
    "ConfigNotFoundError",
    "ConfigValidationError",
    "ConfigCircularReferenceError",
    "ConfigPathNotFoundError",
    "ConfigEnvVarError",
    "ConfigMountError",
]
