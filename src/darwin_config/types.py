"""
Type definitions for configuration structures.
"""

from typing import Any, Dict, List, TypedDict, Union

# Functional syntax is used because "import" is a Python keyword and cannot be
# an attribute name inside a class body, yet it is the directive name in config files.
ConfigFile = TypedDict(
    "ConfigFile",
    {
        "mount": str,
        "import": Union[str, List[str]],
        "merge": Union[str, List[str]],
        "schema": Union[Dict[str, Any], str],
    },
    total=False,
)

__all__ = ["ConfigFile"]
