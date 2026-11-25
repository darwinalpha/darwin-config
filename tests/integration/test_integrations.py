"""L1 framework adapters: Flask, Django and Pydantic data adaptation."""

import sys
import types
from pathlib import Path
from typing import Any, Dict

import pytest

from darwin_config import init_config
from darwin_config.integrations import django as django_adapter
from darwin_config.integrations import flask as flask_adapter
from darwin_config.integrations import pydantic as pydantic_adapter
from tests.conftest import write_json


class FakeFlaskApp:
    """Minimal duck-typed stand-in for a Flask application."""

    def __init__(self) -> None:
        self.config: Dict[str, Any] = {"DEBUG": False}


@pytest.fixture
def loaded_config(config_dir: Path) -> None:
    write_json(config_dir / "app.json", {
        "flask": {"SECRET_KEY": "s3cret", "DEBUG": True},
        "django": {"DEBUG": True, "ALLOWED_HOSTS": ["localhost"], "lowercase_key": "ignored"},
        "service": {"flask_timeout": 30, "flask_host": "localhost"},
        "app": {"name": "demo", "port": 8080},
    })
    init_config([str(config_dir / "app.json")])


def test_flask_adapter_updates_app_config(loaded_config: None) -> None:
    app = FakeFlaskApp()
    applied = flask_adapter.apply_flask_config(app)
    assert applied == {"SECRET_KEY": "s3cret", "DEBUG": True}
    assert app.config["SECRET_KEY"] == "s3cret"
    assert app.config["DEBUG"] is True


def test_flask_adapter_supports_prefix_and_uppercase(loaded_config: None) -> None:
    app = FakeFlaskApp()
    applied = flask_adapter.apply_flask_config(app, "service", prefix="flask_", uppercase=True)
    assert applied == {"TIMEOUT": 30, "HOST": "localhost"}
    assert app.config["TIMEOUT"] == 30


def test_flask_adapter_accepts_explicit_source(loaded_config: None) -> None:
    app = FakeFlaskApp()
    flask_adapter.apply_flask_config(app, source={"DEBUG": True})
    assert app.config["DEBUG"] is True


def test_flask_adapter_rejects_non_updatable_config(loaded_config: None) -> None:
    class BadApp:
        config = object()

    with pytest.raises(TypeError, match="update"):
        flask_adapter.apply_flask_config(BadApp())


def test_django_settings_filters_uppercase(loaded_config: None) -> None:
    settings = django_adapter.django_settings()
    assert settings == {"DEBUG": True, "ALLOWED_HOSTS": ["localhost"]}
    assert "lowercase_key" not in settings


def test_django_settings_can_uppercase_keys(loaded_config: None) -> None:
    settings = django_adapter.django_settings("service", uppercase=True)
    assert settings == {"FLASK_TIMEOUT": 30, "FLASK_HOST": "localhost"}


def test_apply_django_settings_updates_namespace(loaded_config: None) -> None:
    namespace = types.SimpleNamespace()
    applied = django_adapter.apply_django_settings(namespace)
    assert applied == {"DEBUG": True, "ALLOWED_HOSTS": ["localhost"]}
    assert namespace.DEBUG is True
    assert not hasattr(namespace, "lowercase_key")


def test_apply_django_settings_updates_module_dict(loaded_config: None) -> None:
    module = types.ModuleType("fake_settings")
    django_adapter.apply_django_settings(module)
    assert module.DEBUG is True
    assert vars(module)["ALLOWED_HOSTS"] == ["localhost"]


def test_integrations_package_import_is_lazy() -> None:
    import darwin_config.integrations as integrations

    assert integrations.__all__ == []
    assert not hasattr(integrations, "TypeAdapter")


def test_pydantic_adapter_validates_typed_model(loaded_config: None) -> None:
    pytest.importorskip("pydantic", reason="pydantic extra not installed")
    from pydantic import BaseModel

    class Settings(BaseModel):
        name: str
        port: int

    settings = pydantic_adapter.validate_with_pydantic(Settings, "app")
    assert settings.name == "demo"
    assert settings.port == 8080


def test_pydantic_adapter_accepts_explicit_source(loaded_config: None) -> None:
    pytest.importorskip("pydantic", reason="pydantic extra not installed")
    from pydantic import BaseModel

    class Settings(BaseModel):
        name: str

    settings = pydantic_adapter.validate_with_pydantic(Settings, source={"name": "inline"})
    assert settings.name == "inline"


def test_pydantic_adapter_reports_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = __import__

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "pydantic":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    monkeypatch.delitem(sys.modules, "pydantic", raising=False)
    with pytest.raises(ImportError, match=r"darwin-config\[pydantic\]"):
        pydantic_adapter.validate_with_pydantic(dict, source={"a": 1})
