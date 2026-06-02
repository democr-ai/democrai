from __future__ import annotations

from types import SimpleNamespace

import democrai.sdk.client as client_mod
import democrai.sdk.database as database_mod
import democrai.sdk.access as access_mod
import democrai.sdk.ai as ai_mod
import democrai.sdk.auth as auth_mod
import democrai.sdk.dependencies as dependencies_mod
import democrai.sdk.effects as effects_mod
import democrai.sdk.engines as engines_mod
import democrai.sdk.events as events_mod
import democrai.sdk.extractors as extractors_mod
import democrai.sdk.hooks as hooks_mod
import democrai.sdk.i18n as i18n_mod
import democrai.sdk.knowledge as knowledge_mod
import democrai.sdk.media as media_mod
import democrai.sdk.models as models_mod
import democrai.sdk.module_decorators as module_decorators_mod
import democrai.sdk.pages as pages_mod
import democrai.sdk.system as system_mod
import democrai.sdk.tasks as tasks_mod
import democrai.sdk.ui as ui_mod


def test_sdk_client_missing_user_debug_and_proxy_resolution(monkeypatch):
    debug_calls = []
    monkeypatch.setattr(
        client_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(debug=lambda message: debug_calls.append(message))
        ),
    )
    monkeypatch.setattr(client_mod, "to_optional_int", lambda _v: None)
    monkeypatch.setattr(
        database_mod,
        "ModuleDataStore",
        lambda user_id, module_name, organization_id=None, access_level=3: SimpleNamespace(
            user_id=user_id,
            module_name=module_name,
            organization_id=organization_id,
            access_level=access_level,
        ),
    )
    monkeypatch.setattr(
        database_mod,
        "Database",
        lambda store, base: SimpleNamespace(store=store, base=base),
    )
    monkeypatch.setattr(database_mod, "get_module_base", lambda module_name: f"base:{module_name}")
    monkeypatch.setattr(auth_mod, "AuthSDK", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(models_mod, "CoreModelsSDK", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(ui_mod, "UI", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(effects_mod, "Effects", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(ai_mod, "AI", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(media_mod, "Media", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(extractors_mod, "Extractors", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(knowledge_mod, "Knowledge", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(dependencies_mod, "Dependencies", lambda: SimpleNamespace())
    monkeypatch.setattr(engines_mod, "Engines", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(access_mod, "Access", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(system_mod, "System", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(i18n_mod, "I18n", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(pages_mod, "Pages", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(hooks_mod, "Hooks", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(events_mod, "Events", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(tasks_mod, "Tasks", lambda sdk=None: SimpleNamespace(sdk=sdk))
    monkeypatch.setattr(module_decorators_mod, "Decorators", lambda sdk=None: SimpleNamespace(sdk=sdk))

    sdk = client_mod.SDK("/mod", "demo", session={})
    assert sdk.database.store.user_id == 0
    assert debug_calls

    monkeypatch.setattr(client_mod, "_get_default_sdk", lambda: SimpleNamespace(foo="default"))
    proxy = client_mod.SDKProxy()
    token = client_mod.current_sdk.set(None)
    try:
        assert proxy.foo == "default"
    finally:
        client_mod.current_sdk.reset(token)

    token2 = client_mod.current_sdk.set(SimpleNamespace(foo="current"))
    try:
        assert proxy.foo == "current"
    finally:
        client_mod.current_sdk.reset(token2)
