from __future__ import annotations

from types import SimpleNamespace

import democrai.core.application.auth.module_access as module_access_mod


def test_module_access_skips_database_in_setup_and_for_guest_identity(monkeypatch):
    def _unexpected_session():
        raise AssertionError("module access must not open DB for setup or guest")

    monkeypatch.setattr(module_access_mod, "SessionLocal", _unexpected_session)
    monkeypatch.setattr(
        module_access_mod,
        "app_ctx",
        lambda: SimpleNamespace(setup_mode=True),
    )

    assert (
        module_access_mod.is_module_locked_for_user(
            "system",
            user_id=7,
            organization_id=1,
            role="user",
        )
        is False
    )

    monkeypatch.setattr(
        module_access_mod,
        "app_ctx",
        lambda: SimpleNamespace(setup_mode=False),
    )

    assert (
        module_access_mod.is_module_locked_for_session(
            "system",
            {"user": {"id": "guest", "role": "Guest"}},
        )
        is False
    )
