from __future__ import annotations

from types import SimpleNamespace

from democrai.core.infrastructure.session.factory import SessionProviderFactory
from democrai.core.infrastructure.session.providers import MemoryJsonStore
from democrai.core.infrastructure.session.providers import SqlUrlJsonStore
from democrai.core.runtime.foundation.app import app_ctx


def test_session_factory_builds_postgres_ui_state_provider(monkeypatch, tmp_path):
    db_path = tmp_path / "ui_state.db"
    cfg = SimpleNamespace(
        get=lambda key, default=None: {
            "session.identity.provider": "sqlite",
            "session.ui_state.provider": "postgres",
            "session.ui_state.url": f"sqlite:///{db_path}",
            "session.cache.provider": "memory",
        }.get(key, default)
    )
    monkeypatch.setattr(app_ctx(), "config", cfg)

    providers = SessionProviderFactory.create()

    assert isinstance(providers.ui_state, SqlUrlJsonStore)

    providers.ui_state.save("u1", {"current_path": "/chat/index"})
    assert providers.ui_state.load("u1") == {"current_path": "/chat/index"}


def test_session_factory_uses_memory_providers_in_setup_mode(monkeypatch):
    monkeypatch.setattr(app_ctx(), "setup_mode", True)
    monkeypatch.setattr(app_ctx(), "config", None)

    providers = SessionProviderFactory.create()

    assert isinstance(providers.identity, MemoryJsonStore)
    assert isinstance(providers.ui_state, MemoryJsonStore)
    assert isinstance(providers.cache, MemoryJsonStore)
