from __future__ import annotations

import asyncio
from contextvars import ContextVar
from types import SimpleNamespace

import pytest

import democrai.core.application.handler.action_resolution as ar_mod
import democrai.core.application.handler.dispatcher as disp_mod
import democrai.core.application.handler.actions.base_handlers as bh_mod
import democrai.core.application.handler.request as req_mod
from democrai.core.application.request_cycle.engine import _action_context_from_payload


class _Logger:
    def __init__(self):
        self.records = []

    def warning(self, msg):
        self.records.append(("w", msg))

    def error(self, msg):
        self.records.append(("e", msg))

    def debug(self, msg):
        self.records.append(("d", msg))

    def info(self, msg):
        self.records.append(("i", msg))


class _Effects:
    def navigate(self, path, render=True):
        return {"n": path, "r": render}

    def ui_messages(self, msgs):
        return {"ui": msgs}

    def respond(self, *effects):
        return {"effects": list(effects)}

    def refresh_modules(self):
        return {"refresh": True}

    def render(self):
        return {"render": True}

    def set_jwt(self, token):
        return {"jwt": token}


class _CoreSDK:
    def __init__(self):
        self.effects = _Effects()
        self.ui = SimpleNamespace()

    def effect_navigate(self, path, render=True):
        return self.effects.navigate(path, render=render)

    def effect_ui_messages(self, msgs):
        return self.effects.ui_messages(msgs)

    def respond(self, *effects):
        return self.effects.respond(*effects)

    def effect_refresh_modules(self):
        return self.effects.refresh_modules()

    def effect_render(self):
        return self.effects.render()

    def effect_set_jwt(self, token):
        return self.effects.set_jwt(token)


def test_action_context_rejects_client_runtime_keys():
    ctx = _action_context_from_payload(
        {
            "value": "ok",
            "_surface_id": "client-surface",
            "_source_component_id": "client-source",
            "stream_id": "client-stream",
            "session_key": "client-session",
        }
    )

    assert ctx == {"value": "ok"}


def test_action_resolution_paths(monkeypatch):
    logger = _Logger()
    modules = SimpleNamespace(
        get_module=lambda name: SimpleNamespace(path=f"/mods/{name}", name=name) if name == "mod" else None,
        get_all_modules=lambda: [SimpleNamespace(name="mod", path="/mods/mod", actions_module=SimpleNamespace(test_action=lambda *a, **k: {"ok": True}))],
    )
    monkeypatch.setattr(ar_mod, "app_ctx", lambda: SimpleNamespace(modules=modules, logger=logger))

    sdk_ctor_calls = []

    class _SDK:
        def __init__(self, **kwargs):
            sdk_ctor_calls.append(kwargs)
            self.module_name = kwargs["module_name"]

    monkeypatch.setitem(__import__("sys").modules, "democrai.sdk.client", SimpleNamespace(SDK=_SDK))

    sdk = ar_mod.build_module_sdk(SimpleNamespace(path="/p", name="m"), {"current_path": "/x"})
    assert sdk.module_name == "m"

    assert ar_mod.resolve_module_name("a.b") == "a"
    assert ar_mod.resolve_module_name("plain") is None

    core_actions = {"a": lambda *_a, **_k: {}}
    assert ar_mod.resolve_core_action("missing", core_actions, sdk) is None
    resolved = ar_mod.resolve_core_action("a", core_actions, sdk)
    assert resolved.source == "core"

    registry = SimpleNamespace(actions={"mod.x": lambda *_a, **_k: {"ok": True}})
    monkeypatch.setitem(__import__("sys").modules, "democrai.sdk.decorators", SimpleNamespace(get_registry=lambda: registry))
    reg_res = ar_mod.resolve_registry_action("mod.x", {"current_path": "/now"}, fallback_sdk=SimpleNamespace(module_name="core"))
    assert reg_res is not None and reg_res.source == "registry"
    assert ar_mod.resolve_registry_action("missing", {}, fallback_sdk=None) is None

    # legacy cache and invalidation
    ar_mod.invalidate_legacy_action_cache()
    legacy1 = ar_mod.resolve_legacy_action("test_action", {"current_path": "/c1"})
    assert legacy1 is not None and legacy1.source == "legacy"
    legacy2 = ar_mod.resolve_legacy_action("test_action", {"current_path": "/c2"})
    assert legacy2 is not None
    assert len(sdk_ctor_calls) >= 2  # sdk rebuilt using cached module
    assert ar_mod.resolve_legacy_action("missing_action", {}) is None

    ar_mod.invalidate_legacy_action_cache("mod")
    assert "mod" not in ar_mod._legacy_action_cache

    monkeypatch.setattr(ar_mod, "get_required_permissions", lambda handler: ["p1"])
    monkeypatch.setattr(ar_mod, "check_access", lambda required, permissions: True)
    assert ar_mod.check_action_permissions("x", lambda: None, ["p1"]) is None
    monkeypatch.setattr(ar_mod, "check_access", lambda required, permissions: False)
    denied = ar_mod.check_action_permissions("x", lambda: None, [])
    assert denied["error"] == "permission_denied"
    assert ar_mod.unknown_action_response("x")["error"] == "unknown_action"
    err = ar_mod.action_execution_error("x", RuntimeError("boom"), source="core")
    assert err["effects"][0]["type"] == "notify"


@pytest.mark.asyncio
async def test_dispatcher_main_paths(monkeypatch):
    logger = _Logger()
    module_runtime = SimpleNamespace(
        invoke=lambda **kwargs: asyncio.sleep(0, result={"session": {"k": "v"}, "result": {"ok": True}})
    )
    modules = SimpleNamespace(get_module=lambda name: SimpleNamespace(name=name) if name == "mod" else None)
    monkeypatch.setattr(disp_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, modules=modules))

    current_sdk = ContextVar("current_sdk", default=None)
    monkeypatch.setitem(__import__("sys").modules, "democrai.sdk.client", SimpleNamespace(current_sdk=current_sdk))
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(build_module_reuse_key=lambda name, session: "rk", get_module_runtime=lambda: module_runtime),
    )

    dispatcher = disp_mod.ActionDispatcher()
    dispatcher.register_action("democrai.core.ok", lambda ctx, session, sdk: asyncio.sleep(0, result={"core": True}))

    base_sdk = SimpleNamespace(module_name="core")

    monkeypatch.setattr(disp_mod, "resolve_core_action", lambda action_name, core_actions, sdk: ar_mod.ResolvedAction("core", lambda ctx, session, sdk: asyncio.sleep(0, result={"ok": "core"}), sdk) if action_name == "democrai.core.ok" else None)
    monkeypatch.setattr(disp_mod, "resolve_registry_action", lambda action_name, session, sdk: None)
    monkeypatch.setattr(disp_mod, "resolve_legacy_action", lambda action_name, session: None)
    monkeypatch.setattr(disp_mod, "check_action_permissions", lambda action_name, handler, permissions: None)
    monkeypatch.setattr(
        disp_mod,
        "unknown_action_response",
        lambda action_name: {"ok": False, "type": "error", "error": "unknown_action", "details": action_name},
    )
    monkeypatch.setattr(
        disp_mod,
        "action_execution_error",
        lambda action_name, exc, source: {
            "ok": False,
            "type": "error",
            "error": "action_execution_failed",
            "details": str(exc),
        },
    )

    out_core = await dispatcher.dispatch("democrai.core.ok", {"x": 1}, {}, [], base_sdk)
    assert out_core == {"ok": "core"}

    # module runtime branch
    monkeypatch.setattr(disp_mod, "resolve_core_action", lambda *a, **k: None)
    monkeypatch.setattr(
        disp_mod,
        "resolve_registry_action",
        lambda action_name, session, sdk: ar_mod.ResolvedAction("registry", lambda ctx, session, sdk: asyncio.sleep(0, result={"fallback": True}), SimpleNamespace(module_name="mod")),
    )
    session = {}
    out_runtime = await dispatcher.dispatch("mod.action", {"a": 1}, session, [], base_sdk)
    assert out_runtime == {"ok": True}
    assert session == {"k": "v"}

    # runtime non-dict response
    module_runtime2 = SimpleNamespace(invoke=lambda **kwargs: asyncio.sleep(0, result=[1, 2]))
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(build_module_reuse_key=lambda name, session: "rk", get_module_runtime=lambda: module_runtime2),
    )
    out_runtime2 = await dispatcher.dispatch("mod.action", {}, {}, [], base_sdk)
    assert out_runtime2 == [1, 2]

    # unknown action
    monkeypatch.setattr(disp_mod, "resolve_registry_action", lambda *a, **k: None)
    monkeypatch.setattr(disp_mod, "resolve_legacy_action", lambda *a, **k: None)
    out_unknown = await dispatcher.dispatch("missing", {}, {}, [], base_sdk)
    assert out_unknown["error"] == "unknown_action"

    # denied permissions
    monkeypatch.setattr(disp_mod, "resolve_core_action", lambda *a, **k: ar_mod.ResolvedAction("core", lambda *a, **k: asyncio.sleep(0, result={}), base_sdk))
    monkeypatch.setattr(disp_mod, "check_action_permissions", lambda *a, **k: {"error": "permission_denied"})
    out_denied = await dispatcher.dispatch("x", {}, {}, [], base_sdk)
    assert out_denied["error"] == "permission_denied"

    # handler exception
    monkeypatch.setattr(disp_mod, "check_action_permissions", lambda *a, **k: None)
    monkeypatch.setattr(disp_mod, "resolve_core_action", lambda *a, **k: ar_mod.ResolvedAction("core", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")), base_sdk))
    out_err = await dispatcher.dispatch("x", {}, {}, [], base_sdk)
    assert out_err["error"] == "action_execution_failed"

    # outer dispatcher exception
    monkeypatch.setattr(disp_mod, "resolve_core_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("outer")))
    out_outer = await dispatcher.dispatch("x", {}, {}, [], base_sdk)
    assert out_outer["error"] == "dispatcher_exception"


def test_base_handlers_helpers_and_branches(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(bh_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    sdk = _CoreSDK()
    session = {}
    out_nav = asyncio.run(bh_mod.nav({"path": "/x", "render": True}, session, sdk))
    assert out_nav["effects"][0]["n"] == "/x"
    out_nav_sdk_no_render = asyncio.run(
        bh_mod.nav({"path": "/x", "render": False}, session, sdk)
    )
    assert len(out_nav_sdk_no_render["effects"]) == 1
    out_nav_yes_render = asyncio.run(
        bh_mod.nav({"path": "/x", "render": "yes"}, session, sdk)
    )
    assert out_nav_yes_render["effects"][0]["r"] is True
    out_nav_unknown_render = asyncio.run(
        bh_mod.nav({"path": "/x", "render": "maybe"}, session, sdk)
    )
    assert out_nav_unknown_render["effects"][0]["r"] is True
    assert asyncio.run(bh_mod.navigate({"path": "/x"}, session, sdk))

    monkeypatch.setattr(bh_mod.observability_service, "record_auth_event", lambda **kwargs: None)
    monkeypatch.setattr(bh_mod, "clear_post_login_path", lambda session: session.pop("post_login", None))
    original_resolve_user_language = bh_mod._resolve_user_language
    monkeypatch.setattr(bh_mod, "_resolve_user_language", lambda session, uid: "it")
    sess = {"current_path": "/home", "user": {"id": 5}, "post_login": "/x"}
    out_logout = asyncio.run(bh_mod.logout({}, sess, sdk))
    assert out_logout["effects"][0]["refresh"] is True
    monkeypatch.setattr(bh_mod, "_resolve_user_language", original_resolve_user_language)

    assert bh_mod._coerce_priority("x", default=9) == 9
    assert bh_mod._normalize_language("IT") == "it"
    assert bh_mod._normalize_language("zz") == "en"
    assert bh_mod._client_stubs()["access_levels"][0]["value"] == "super"

    # resolve language branches
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.services.translation", SimpleNamespace(get_translation_service=lambda: SimpleNamespace(get_user_language=lambda uid: "fr", _default_language="en")))
    assert bh_mod._resolve_user_language({"user_language": "de"}, 1) == "de"
    assert bh_mod._resolve_user_language({"user": {"language": "es"}}, 1) == "es"
    assert bh_mod._resolve_user_language({}, 1) == "fr"

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.services.translation", SimpleNamespace(get_translation_service=lambda: SimpleNamespace(get_user_language=lambda uid: (_ for _ in ()).throw(RuntimeError("x")), _default_language="en")))
    assert bh_mod._resolve_user_language({}, 1) == "en"
    assert bh_mod._resolve_user_language({}, None) == "en"


def test_set_user_language_guest_session_only():
    sdk = _CoreSDK()
    session = {"user": {"id": "guest", "role": "Guest"}}

    out = asyncio.run(bh_mod.set_user_language({"value": "it"}, session, sdk))

    assert session["user"]["language"] == "it"
    assert session["user_language"] == "it"
    state = out["effects"][0]["ui"][0]["stateUpdate"]["values"]
    assert state["/core/user/language"] == "it"
    assert out["effects"][1]["render"] is True


def test_set_user_language_authenticated_persists_profile():
    updated_payloads = []
    sdk = _CoreSDK()
    sdk.models = SimpleNamespace(
        users=SimpleNamespace(
            update=lambda user_id, payload: updated_payloads.append((user_id, payload))
            or {"id": user_id, **payload}
        )
    )
    session = {"user": {"id": 7, "role": "user"}}

    out = asyncio.run(bh_mod.set_user_language({"value": "fr"}, session, sdk))

    assert updated_payloads == [(7, {"language": "fr"})]
    assert session["user"]["language"] == "fr"
    assert session["user_language"] == "fr"
    assert out["effects"][0]["ui"][0]["stateUpdate"]["values"]["/core/user/language"] == "fr"


def test_set_user_language_rejects_invalid_language():
    sdk = _CoreSDK()
    session = {"user": {"id": "guest", "role": "Guest"}}

    out = asyncio.run(bh_mod.set_user_language({"value": "zz"}, session, sdk))

    assert out["error"] == "invalid_language"
    assert "user_language" not in session


def test_background_task_get_updates_global_store():
    sdk = _CoreSDK()
    sdk.models = SimpleNamespace(
        background_tasks=SimpleNamespace(
            view=lambda task_id: {
                "id": task_id,
                "label": "Import",
                "module": "chat",
                "status": "completed",
                "progress": 1.0,
                "updated_at": "2026-05-29T17:00:00",
                "checkpoint": None,
                "result": '{"ok": true}',
                "error": None,
            }
        )
    )

    out = asyncio.run(bh_mod.background_task_get({"task_id": "task-1"}, {}, sdk))

    message = out["effects"][0]["ui"][0]
    values = message["stateUpdate"]["values"]
    assert message["stateUpdate"]["scope"] == "global"
    assert values["/background_tasks/task-1"] == {
        "taskId": "task-1",
        "label": "Import",
        "module": "chat",
        "status": "completed",
        "progress": 1.0,
        "updatedAt": "2026-05-29T17:00:00",
        "result": {"ok": True},
    }


def test_core_default_actions_include_background_task_get():
    assert disp_mod._get_core_default_actions()["background_task.get"] is bh_mod.background_task_get


def test_base_handlers_modules_list_and_orchestration(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(bh_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(bh_mod, "_resolve_user_language", lambda session, user_id: "en")

    class _Cond:
        @staticmethod
        def bound(path):
            return f"b:{path}"

        @staticmethod
        def OR(*args):
            return ("OR", args)

        def __init__(self, a, op, b):
            self.value = (a, op, b)

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.platform.utils.conditions", SimpleNamespace(Condition=_Cond))

    module_auth = SimpleNamespace(
        name="auth",
        label="Auth",
        icon="i-auth",
        sidebar_init_declared=False,
        sidebar_entries=[],
        sidebar_position="bottom",
        priority=1,
        actions_module=None,
        authenticated_label=None,
        authenticated_icon=None,
    )
    module_sys = SimpleNamespace(
        name="system",
        label="System",
        icon="i-sys",
        sidebar_init_declared=True,
        sidebar_entries=[{"id": "sys", "label": "System", "icon": "i", "action": {"name": "nav", "context": {"path": "/system/index"}}, "active_path": "/system", "position": "top", "visible_for": "authenticated", "priority": 10}],
        sidebar_position="top",
        priority=2,
        actions_module=None,
        authenticated_label="System+",
        authenticated_icon="i2",
    )
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.infrastructure.modules.manager", SimpleNamespace(module_manager=SimpleNamespace(get_all_modules=lambda: [module_auth, module_sys])))
    monkeypatch.setattr(bh_mod, "_check_user_module_access", lambda *_args, **_kwargs: True)

    guest_state = bh_mod._get_modules_list({"user": {}, "current_path": "/"})
    assert "/system/modules/top" in guest_state["stateUpdate"]["values"]

    auth_state = bh_mod._get_modules_list({"user": {"username": "fab", "id": 1}, "current_path": "/system"})
    assert len(auth_state["stateUpdate"]["values"]["/system/modules/top"]) == 1

    declared_bad = SimpleNamespace(name="bad", sidebar_init_declared=True, sidebar_entries="not-a-list")
    assert bh_mod._resolve_sidebar_entries(declared_bad) == []

    legacy_custom = SimpleNamespace(
        name="custom",
        label="Custom",
        icon="ic",
        sidebar_position="top",
        priority=4,
        authenticated_label="Custom+",
        authenticated_icon="ic+",
    )
    legacy_entry = bh_mod._legacy_sidebar_entries(legacy_custom)[0]
    assert legacy_entry["authenticated_label"] == "Custom+"
    assert legacy_entry["authenticated_icon"] == "ic+"

    sdk = _CoreSDK()
    out = asyncio.run(bh_mod.modules_list({}, {"user": {}}, sdk))
    assert out["effects"][0]["ui"]

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.ai.orchestrator", SimpleNamespace(model_orchestrator=SimpleNamespace(get_provider_for_objective=lambda objective, confirm_swap=False: asyncio.sleep(0, result={"status": "ok", "provider": SimpleNamespace(model_name="m1")}))))
    session = {}
    orch_ok = asyncio.run(bh_mod.orchestration_test({"objective": "chat"}, session, sdk))
    assert orch_ok["effects"][0]["render"] is True
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.ai.orchestrator", SimpleNamespace(model_orchestrator=SimpleNamespace(get_provider_for_objective=lambda objective, confirm_swap=False: asyncio.sleep(0, result={"status": "need_confirmation"}))))
    orch_need = asyncio.run(bh_mod.orchestration_test({"objective": "chat"}, session, sdk))
    assert orch_need["status"] == "need_confirmation"


def test_base_handlers_modules_list_visibility_and_fallbacks(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(bh_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(bh_mod, "_resolve_user_language", lambda session, user_id: "en")
    monkeypatch.setattr(
        bh_mod,
        "_check_user_module_access",
        lambda module_name, *_args, **_kwargs: module_name != "blocked",
    )

    class _Cond:
        @staticmethod
        def bound(path):
            return f"b:{path}"

        @staticmethod
        def OR(*args):
            return ("OR", args)

        def __init__(self, a, op, b):
            self.value = (a, op, b)

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.utils.conditions",
        SimpleNamespace(Condition=_Cond),
    )

    blocked = SimpleNamespace(
        name="blocked",
        label="Blocked",
        icon="x",
        sidebar_init_declared=False,
        sidebar_entries=[],
        sidebar_position="top",
        priority=1,
    )
    guest_module = SimpleNamespace(
        name="guest_only",
        label="Guest",
        icon="g",
        sidebar_init_declared=True,
        sidebar_entries=[
            {
                "id": "g1",
                "label": "Guest Base",
                "icon": "gb",
                "guest_label": "Guest Label",
                "guest_icon": "gi",
                "guest_action": {"name": "nav", "context": {"path": "/guest/home"}},
                "visible_for": "all",
                "position": "top",
                "priority": "8",
            },
            {"id": "skip-auth", "label": "SkipMe", "visible_for": "authenticated"},
        ],
        sidebar_position="top",
        priority=5,
    )
    auth_module = SimpleNamespace(
        name="auth_only",
        label="Auth Base",
        icon="ab",
        sidebar_init_declared=True,
        sidebar_entries=[
            {
                "id": "a1",
                "label": "Auth Label Base",
                "icon": "abi",
                "authenticated_label": "Auth Label",
                "authenticated_icon": "ai",
                "authenticated_action": {"name": "nav", "context": {"path": "/auth/home"}},
                "visible_for": "authenticated",
                "position": "bottom",
                "priority": 3,
            },
            {"id": "skip-guest", "label": "SkipGuest", "visible_for": "guest"},
            {
                "id": "path-fallback",
                "label": "PathFallback",
                "action": {"name": "nav", "context": {"path": "/auth/fallback"}},
                "active_path": "",
                "visible_for": "authenticated",
                "position": "top",
            },
            {
                "id": "module-fallback",
                "label": "ModuleFallback",
                "action": {"name": "open"},
                "visible_for": "authenticated",
                "position": "top",
            },
        ],
        sidebar_position="top",
        priority=2,
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.modules.manager",
        SimpleNamespace(
            module_manager=SimpleNamespace(
                get_all_modules=lambda: [blocked, guest_module, auth_module]
            )
        ),
    )

    guest_payload = bh_mod._get_modules_list({"user": {"username": "guest"}})
    guest_top = guest_payload["stateUpdate"]["values"]["/system/modules/top"]
    assert any(item["label"] == "Guest Label" and item["icon"] == "gi" for item in guest_top)
    assert all(item["id"] != "skip-auth" for item in guest_top)

    auth_payload = bh_mod._get_modules_list({"user": {"username": "u", "id": 9}})
    auth_top = auth_payload["stateUpdate"]["values"]["/system/modules/top"]
    auth_bottom = auth_payload["stateUpdate"]["values"]["/system/modules/bottom"]
    assert any(item["id"] == "a1" and item["label"] == "Auth Label" and item["icon"] == "ai" for item in auth_bottom)
    assert all(item["id"] != "skip-guest" for item in auth_top + auth_bottom)
    assert any(item["id"] == "path-fallback" for item in auth_top)
    assert any(item["id"] == "module-fallback" for item in auth_top)

    out_plain = asyncio.run(bh_mod.modules_list({}, {"user": {}}, _CoreSDK()))
    assert out_plain["effects"][0]["ui"]

    service_calls = []
    monkeypatch.setattr(
        bh_mod,
        "app_ctx",
        lambda: SimpleNamespace(setup_mode=True, logger=logger),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.services.translation",
        SimpleNamespace(get_translation_service=lambda: service_calls.append("called")),
    )
    assert bh_mod._resolve_user_language({"user": {"username": "guest"}}, None) == "en"
    assert service_calls == []


def test_request_get_session_extra_branch(monkeypatch):
    core = req_mod.Core()
    monkeypatch.setattr(core.session_service, "get_or_create", lambda user, role: {"user": user, "role": role})

    # req_ctx exception branch
    monkeypatch.setattr(req_mod, "req_ctx", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    got = core.get_session("u", "r")
    assert isinstance(got, dict)
