from __future__ import annotations

import builtins

from democrai.core.platform.config.base import ConfigProvider
from democrai.core.platform.config.yaml_config import YamlConfigProvider


def test_config_provider_abstract_method_bodies_are_executable():
    # Exercise abstract stubs to cover their default pass bodies.
    assert ConfigProvider.get(None, "x") is None
    assert ConfigProvider.set(None, "x", 1) is None
    assert ConfigProvider.save(None) is None


def test_yaml_provider_load_get_set_and_save(tmp_path):
    config_file = tmp_path / "cfg" / "app.yaml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("db:\n  url: sqlite:///app.db\n", encoding="utf-8")

    provider = YamlConfigProvider(str(config_file))
    assert provider.get("db.url") == "sqlite:///app.db"
    assert provider.get("db.missing", "fallback") == "fallback"

    provider.set("runtime.debug.enabled", True)
    assert provider.get("runtime.debug.enabled") is True

    provider.set("runtime.debug", "overridden")
    provider.set("runtime.debug.enabled", False)
    assert provider.get("runtime.debug.enabled") is False

    provider.save()
    reloaded = YamlConfigProvider(str(config_file))
    assert reloaded.get("runtime.debug.enabled") is False


def test_yaml_provider_load_and_save_error_paths(tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: messages.append(" ".join(str(a) for a in args)))

    config_file = tmp_path / "broken.yaml"
    config_file.write_text(":\n- invalid", encoding="utf-8")
    provider = YamlConfigProvider(str(config_file))
    assert provider.get("anything", "default") == "default"
    assert any("Error loading" in msg for msg in messages)

    def _boom_open(*_args, **_kwargs):
        raise OSError("cannot-open")

    monkeypatch.setattr(builtins, "open", _boom_open)
    provider.save()
    assert any("Error saving" in msg for msg in messages)


def test_yaml_provider_load_no_file_path(tmp_path):
    provider = YamlConfigProvider(str(tmp_path / "missing.yaml"))
    assert provider.get("x", 7) == 7
