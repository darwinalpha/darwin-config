"""Run every sample config under examples/ to demonstrate darwin-config's capabilities.

Usage:
    PYTHONPATH=src py -3.12 examples/demo.py
Or after installation:
    python examples/demo.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from darwin_config import (  # noqa: E402
    add_config,
    config_trace,
    get_config,
    init_config,
    try_config,
)


def show(label: str, value: object) -> None:
    print(f"  {label:<38} = {value!r}")


def run(fmt: str, suffix: str) -> None:
    base = HERE / fmt
    print(f"\n=== {fmt.upper()} examples ===")

    # 1. Basics + environment variables
    init_config(files=[str(base / f"01-basic.{suffix}")], mount="config")
    show("app.name", get_config("config.app.name"))
    show("database.host (env/default)", get_config("config.database.host"))
    show("database.port (env/default)", get_config("config.database.port"))

    # 2. Layered import (base <- common <- app, overridden layer by layer)
    init_config(files=[str(base / "layered" / f"app.{suffix}")], mount="config")
    show("server (3-layer deep merge)", get_config("config.server"))
    show("features", get_config("config.features"))

    # 3. Reuse objects as merge templates
    init_config(files=[str(base / f"03-merge.{suffix}")], mount="config")
    show("clients.public", get_config("config.clients.public"))
    show("clients.private", get_config("config.clients.private"))

    # 4. Inline schema validation + defaults
    init_config(files=[str(base / f"04-schema-inline.{suffix}")], mount="config", validate=True)
    show("schema default mode", get_config("config.mode"))

    # 5. External schema file (which itself imports another schema)
    init_config(files=[str(base / f"05-schema-external.{suffix}")], mount="config", validate=True)
    show("external schema default port", get_config("config.port"))

    # 6. this / root / calc / env expressions
    init_config(
        files=[
            str(base / f"06-expressions.{suffix}"),
            str(base / f"06-expressions-peer.{suffix}"),
        ],
        mount="config",
    )
    show("this chain", get_config("config.storage.archive"))
    show("calc", get_config("config.limits.total"))
    show("root cross-file", get_config("config.token_copy"))

    # 7. ~ escaped reserved words
    init_config(files=[str(base / f"07-escape.{suffix}")], mount="config")
    show("~import as business field", get_config("config.import"))
    show("~schema as business field", get_config("config.schema"))

    # 8. mount + add_config + alias + tracing
    init_config(files=[str(base / f"01-basic.{suffix}")], mount="config")
    add_config(str(base / f"08-mount-adapter.{suffix}"), mount="primary.demo")
    show("mounted token", get_config("adapter.demo.auth.token"))
    show("alias token", get_config("primary.demo.auth.token"))
    show("try_config fallback", try_config("config.nope", "config.app.name", default="missing"))
    print(f"  trace: {config_trace('adapter.demo.auth.token')}")


def main() -> None:
    run("json", "json")
    if importlib.util.find_spec("yaml") is None:
        print("\n[skip] YAML examples: run pip install 'darwin-config[yaml]' first")
    else:
        run("yaml", "yaml")
    # TOML reading uses the standard library tomllib; no optional dependency needed.
    run("toml", "toml")


if __name__ == "__main__":
    main()
