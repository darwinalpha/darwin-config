"""Env-var interpolation tests: config only consumes env vars; it never manages the process env."""

from pathlib import Path

from darwin_config import get_config, init_config
from tests.conftest import write_json


def test_env_in_config(config_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("DC_DB_HOST", "prod.db")
    file = write_json(config_dir / "s.json", {"host": "${DC_DB_HOST}"})
    init_config(files=[str(file)], mount="config")
    assert get_config("config.host") == "prod.db"


def test_env_values_injection_takes_priority(config_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("DC_TOKEN", "from-env")
    file = write_json(config_dir / "s.json", {"token": "${DC_TOKEN}"})
    init_config(files=[str(file)], mount="config", values={"DC_TOKEN": "from-values"})
    assert get_config("config.token") == "from-values"
