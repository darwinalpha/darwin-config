"""Integration tests: every sample under examples/ loads and behaves as documented."""

import importlib.util
from pathlib import Path

import pytest

from darwin_config import add_config, config_trace, get_config, init_config, try_config

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("DB_HOST", "DB_PORT", "DEBUG", "EXPRESSIONS_TOKEN", "ADAPTER_TOKEN"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    ("fmt", "suffix"),
    [
        ("json", "json"),
        pytest.param(
            "yaml",
            "yaml",
            marks=pytest.mark.skipif(
                importlib.util.find_spec("yaml") is None, reason="PyYAML not installed"
            ),
        ),
        ("toml", "toml"),
    ],
)
def test_all_examples(fmt: str, suffix: str) -> None:
    base = EXAMPLES / fmt

    init_config(files=[str(base / f"01-basic.{suffix}")], mount="config")
    assert get_config("config.app.name") == "demo-service"
    assert get_config("config.database.host") == "localhost"
    assert get_config("config.database.port") == "5432"  # env var values stay strings

    init_config(files=[str(base / "layered" / f"app.{suffix}")], mount="config")
    assert get_config("config.server") == {
        "host": "0.0.0.0",
        "port": 9090,
        "timeout": 60,
        "workers": 8,
    }
    assert get_config("config.features") == {"cache": False, "metrics": True}

    init_config(files=[str(base / f"03-merge.{suffix}")], mount="config")
    assert get_config("config.clients.public") == {
        "timeout": 10,
        "retry": 3,
        "headers": {"Accept": "application/json"},
    }
    assert get_config("config.clients.private")["retry"] == 5
    assert get_config("config.clients.private")["type"] == "bearer"

    init_config(files=[str(base / f"04-schema-inline.{suffix}")], mount="config", validate=True)
    assert get_config("config.mode") == "dev"
    assert get_config("config.port") == 9000

    init_config(files=[str(base / f"05-schema-external.{suffix}")], mount="config", validate=True)
    assert get_config("config.port") == 80
    assert get_config("config.host") == "localhost"

    init_config(
        files=[
            str(base / f"06-expressions.{suffix}"),
            str(base / f"06-expressions-peer.{suffix}"),
        ],
        mount="config",
    )
    assert get_config("config.storage.archive") == "/data/daily/archive"
    assert get_config("config.limits.total") == 12
    assert get_config("config.token_copy") == "dev-token"

    init_config(files=[str(base / f"07-escape.{suffix}")], mount="config")
    assert get_config("config.import") == ["kept", "as", "data"]
    assert get_config("config.schema") == {"name": "mysql"}

    init_config(files=[str(base / f"01-basic.{suffix}")], mount="config")
    add_config(str(base / f"08-mount-adapter.{suffix}"), mount="primary.demo")
    assert get_config("adapter.demo.auth.token") == "local-token"
    assert get_config("primary.demo.auth.token") == "local-token"
    assert try_config("config.nope", "config.app.name") == "demo-service"
    assert str(base / f"08-mount-adapter.{suffix}") in config_trace("adapter.demo.auth.token")
