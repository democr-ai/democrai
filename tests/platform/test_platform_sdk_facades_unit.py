from __future__ import annotations

import contextlib
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import democrai.core.platform.agents.registry as agents_registry_mod
import democrai.sdk.access as access_mod
import democrai.sdk.auth as auth_sdk_mod
import democrai.sdk.decorator_binding as binding_mod
import democrai.sdk.decorator_helpers.action as action_helpers_mod
import democrai.core.application.handler.action_validation as action_validation_mod
import democrai.sdk.decorator_helpers.ui as ui_helpers_mod
import democrai.sdk.dependencies as dependencies_mod
import democrai.sdk.effects as effects_mod
import democrai.sdk.engines as engines_mod
import democrai.sdk.events as events_sdk_mod
import democrai.sdk.extractors as extractors_mod
import democrai.sdk.hooks as hooks_mod
import democrai.sdk.i18n as i18n_mod
import democrai.sdk.knowledge as knowledge_mod
import democrai.sdk.models as models_mod
import democrai.core.platform.utils.discovery as discovery_mod
from democrai.core.runtime.foundation.app import request_context_scope
import democrai.core.platform.utils.system as system_mod


class _Logger:
    def __init__(self):
        self.warnings = []
        self.errors = []
        self.debugs = []
        self.infos = []

    def warning(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)

    def debug(self, msg):
        self.debugs.append(msg)

    def info(self, msg):
        self.infos.append(msg)


def test_access_sdk_facade_and_sync(monkeypatch):
    calls = []

    monkeypatch.setattr(access_mod, "check_access", lambda req, perms: req == perms)
    monkeypatch.setattr(
        access_mod,
        "external_access",
        SimpleNamespace(
            EXTERNAL_RESOURCE_NETWORK="network",
            EXTERNAL_RESOURCE_FILESYSTEM="filesystem",
            EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY="sysdep",
            check_external_access=lambda **kwargs: calls.append(("check", kwargs)) or SimpleNamespace(allowed=True),
            approve_for_session=lambda **kwargs: calls.append(("approve_session", kwargs)),
            approve_permanently=lambda **kwargs: calls.append(("approve_perm", kwargs)),
            deny_external_access=lambda **kwargs: calls.append(("deny", kwargs)),
            is_permanently_approved=lambda **kwargs: kwargs["target"] == "ok",
            can_manage_external_access=lambda **kwargs: kwargs.get("access_level") == 1,
        ),
    )

    sdk = SimpleNamespace(module_name="mod")
    access = access_mod.Access(sdk)

    assert access.check_permissions(["a"], ["a"])
    assert access.check_external_access(
        resource_type="network",
        operation="receive",
        target="https://x",
    ).allowed
    assert access.require_external_access(
        resource_type="network",
        operation="receive",
        target="https://x",
        resume_action="mod.resume",
        resume_context={"id": 1},
    ).allowed
    access.approve_for_session(resource_type="network", operation="receive", target="https://x")
    access.approve_permanently(resource_type="network", operation="receive", target="https://x")
    access.deny_external_access(resource_type="network", operation="receive", target="https://x")
    assert access.is_permanently_approved(resource_type="network", operation="receive", target="ok") is True
    assert access.can_manage_external_access(
        user_id=1,
        role="super",
        access_level=1,
        organization_id=2,
        permissions=["x"],
    )

    approvals_by_scope = {}
    app_module = __import__("democrai.core.runtime.foundation.app", fromlist=["x"])
    monkeypatch.setattr(app_module, "app_ctx", lambda: SimpleNamespace(network=SimpleNamespace(_session_external_approvals=approvals_by_scope)))
    monkeypatch.setattr(app_module, "req_ctx", lambda: SimpleNamespace(session_key="sess-1", user=77))

    access.sync_session_external_approvals({"a", "b", "c"}, session={"user": {"id": 12}})
    assert approvals_by_scope["session:sess-1"] == {"a", "b", "c"}
    assert approvals_by_scope["user:12"] == {"a", "b", "c"}

    # network approvals map missing/invalid -> no-op
    monkeypatch.setattr(app_module, "app_ctx", lambda: SimpleNamespace(network=SimpleNamespace(_session_external_approvals=None)))
    access.sync_session_external_approvals({"x"}, session={"user": {"id": 1}})

    # req_ctx failure + non-set scoped entries -> should not explode
    monkeypatch.setattr(
        app_module,
        "app_ctx",
        lambda: SimpleNamespace(network=SimpleNamespace(_session_external_approvals={"session:s-key": [], "user:7": []})),
    )
    monkeypatch.setattr(app_module, "req_ctx", lambda: (_ for _ in ()).throw(RuntimeError("ctx")))
    access.sync_session_external_approvals({"z"}, session={"user": {"id": 7}})


def test_auth_sdk_paths(monkeypatch):
    monkeypatch.setattr(auth_sdk_mod, "create_access_token", lambda data, exp=None: f"tok:{data.get('user_id')}")
    monkeypatch.setattr(
        auth_sdk_mod,
        "build_token_payload",
        lambda user_info: {
            "sub": str(user_info["id"]),
            "user_id": int(user_info["id"]),
            "role": str(user_info.get("role") or "user"),
            "access_level": user_info.get("access_level"),
            "organization_id": user_info.get("organization_id"),
        },
    )

    sdk = SimpleNamespace(session={"user": {"id": 10}})
    auth = auth_sdk_mod.AuthSDK(sdk)

    assert auth.create_token({"user_id": 1}) == "tok:1"
    payload = auth._build_token_payload({"id": 9, "role": "admin", "access_level": 1, "organization_id": "3"})
    assert payload["user_id"] == 9

    monkeypatch.setattr(auth_sdk_mod, "req_ctx", lambda: SimpleNamespace(user=10))
    monkeypatch.setattr(
        auth_sdk_mod,
        "refresh_session_token",
        lambda *, session_user_id, requester_id: {
            "ok": session_user_id == requester_id == 10,
            "error": "unauthorized_refresh" if requester_id != session_user_id else None,
        },
    )
    ok = auth.refresh_current_session_token()
    assert ok["ok"] is True

    auth2 = auth_sdk_mod.AuthSDK(SimpleNamespace(session={}))
    monkeypatch.setattr(
        auth_sdk_mod,
        "refresh_session_token",
        lambda *, session_user_id, requester_id: {
            "ok": False,
            "error": "unauthenticated" if session_user_id is None else "unexpected",
        },
    )
    assert auth2.refresh_current_session_token()["error"] == "unauthenticated"

    monkeypatch.setattr(auth_sdk_mod, "req_ctx", lambda: SimpleNamespace(user=999))
    monkeypatch.setattr(
        auth_sdk_mod,
        "refresh_session_token",
        lambda *, session_user_id, requester_id: {
            "ok": False,
            "error": "unauthorized_refresh",
        },
    )
    assert auth.refresh_current_session_token()["error"] == "unauthorized_refresh"

    monkeypatch.setattr(
        auth_sdk_mod,
        "login_user",
        lambda username, password: {"ok": username == "admin" and password == "secret"},
    )
    assert auth.login("admin", "secret")["ok"] is True

    monkeypatch.setattr(auth_sdk_mod, "req_ctx", lambda: SimpleNamespace(user=10))
    monkeypatch.setattr(
        auth_sdk_mod,
        "refresh_session_token",
        lambda *, session_user_id, requester_id: {
            "ok": False,
            "error": "refresh_failed",
        },
    )
    assert auth.refresh_current_session_token()["error"] == "refresh_failed"


@pytest.mark.asyncio
async def test_events_extractors_hooks_knowledge_engines_effects_models(monkeypatch, tmp_path):
    # Events facade
    sdk = SimpleNamespace(module_name="mod", session={"user": {"id": 1}}, module_path=str(tmp_path), extractors=None, media=None)
    events = events_sdk_mod.Events(sdk)
    assert events.qualify_event_name("x") == "mod.x"
    assert events.qualify_event_name("mod.y") == "mod.y"
    assert events.qualify_event_name(1) == "1"

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.runtime.foundation.registry", SimpleNamespace(module_event_registry=SimpleNamespace(get_definitions=lambda module_name=None: [{"module": module_name}])))
    assert events.get_event_slots("mod")[0]["module"] == "mod"

    captured_emit = []

    async def _emit(name, payload=None, session=None):
        captured_emit.append((name, payload, session))
        return ["ok"]

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.platform.events", SimpleNamespace(emit_module_event=_emit))
    out_emit = await events.emit("evt", payload={"a": 1})
    assert out_emit == ["ok"]
    assert captured_emit[0][0] == "mod.evt"

    # Extractors facade
    sdk.models = SimpleNamespace(extractor_registry=SimpleNamespace(list=lambda **kwargs: {"items": [{"id": 1}] }))
    ext = extractors_mod.Extractors(sdk)
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.knowledge.extractor.manifests", SimpleNamespace(list_extractor_manifests=lambda: [{"name": "e"}]))
    assert ext.list_manifests() == [{"name": "e"}]
    assert ext.list_registered() == [{"id": 1}]

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.knowledge.extractor.resolver",
        SimpleNamespace(
            resolve_active_extractor=lambda **kwargs: {"resolved": kwargs.get("mime_type")},
            extract_with_active_extractor=lambda **kwargs: {"extracted": kwargs.get("filename")},
        ),
    )
    assert ext.resolve(filename="a.pdf")["resolved"] in {"application/pdf", None}
    assert ext.resolve_for_mime_type("text/plain")["resolved"] == "text/plain"
    assert ext.extract(data=b"x", filename="a.txt")["extracted"] == "a.txt"
    assert extractors_mod.Extractors.guess_mime_type("a.unknown") in {None, "application/octet-stream"}

    async def _publish_extractor(**kwargs):
        return kwargs

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.knowledge.extractor.install_events",
        SimpleNamespace(publish_extractor_install_requested=_publish_extractor),
    )
    extractor_runtime_calls = []

    class _ExtractorRuntime:
        async def sync_active_extractors(self):
            extractor_runtime_calls.append("sync")

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.knowledge.extractor.runtime",
        SimpleNamespace(
            get_extractor_runtime=lambda: _ExtractorRuntime(),
            check_extractor_ready_runtime=lambda extractor_id: {
                "extractor_id": extractor_id,
                "ready": True,
            },
        ),
    )
    install_request = await ext.request_install(
        extractor_id="docling",
        install_config={"ocr_engine": "rapidocr"},
    )
    assert install_request["extractor_id"] == "docling"
    assert install_request["install_config"] == {"ocr_engine": "rapidocr"}
    await ext.sync_runtime()
    assert extractor_runtime_calls == ["sync"]
    assert (await ext.check_ready(extractor_id="docling"))["ready"] is True

    # Hooks facade
    hooks = hooks_mod.Hooks(sdk)
    assert hooks.qualify_render_hook_name("slot") == "mod.slot"
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.runtime.foundation.registry", SimpleNamespace(render_hook_registry=SimpleNamespace(get_definitions=lambda module_name=None: [{"module": module_name}])))
    assert hooks.get_render_hook_slots("x")[0]["module"] == "x"

    async def _resolve_hook(name, params=None, session=None):
        return [name, params, session]

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.platform.ui.hooks", SimpleNamespace(resolve_render_hook_components=_resolve_hook))
    out_hook = await hooks.resolve_render_hook("slot", params={"k": 1})
    assert out_hook[0] == "mod.slot"

    # I18n facade
    class _Tx:
        def __init__(self):
            self.loaded = []

        def load_module_locales(self, module_name, locales_path):
            self.loaded.append((module_name, locales_path))

        def get_user_language(self, user_id):
            return "it"

        def t(self, key, lang=None, context=None, module=None):
            return f"{module}:{key}:{lang}"

    tx = _Tx()
    monkeypatch.setattr(i18n_mod, "get_translation_service", lambda: tx)
    (tmp_path / "locales").mkdir(parents=True, exist_ok=True)
    sdk.module_path = str(tmp_path)
    sdk.session = {"user": {"id": 5}, "user_language": "fr"}
    i18n = i18n_mod.I18n(sdk)
    assert i18n.get_user_language() == "it"
    assert i18n.t("k") == "None:k:fr"

    # Knowledge facade
    sdk.media = SimpleNamespace()
    sdk.extractors = SimpleNamespace(
        extract=lambda **kwargs: {"ok": kwargs["path"]},
        resolve=lambda **kwargs: {"resolved": kwargs},
    )
    ingestion = SimpleNamespace(
        ingest_document=lambda **kwargs: {"doc": kwargs["path"]},
        ingest_document_bytes=lambda **kwargs: {"bytes": kwargs["filename"]},
    )
    monkeypatch.setattr(knowledge_mod, "app_ctx", lambda: SimpleNamespace(knowledge_ingestion=ingestion))

    know = knowledge_mod.Knowledge(sdk)
    assert know.extract_document_data("a.pdf")["ok"]
    with pytest.raises(RuntimeError, match="legacy media path resolution was removed"):
        know.extract_document_data("a.pdf", force_path_resolved=True)
    assert know.resolve_registered_extractor(path="a.pdf")["resolved"]["path"] == "a.pdf"
    assert know.extract_with_registered_extractor(data=b"x", filename="a.txt")["ok"] is None
    with request_context_scope(
        {
            "request_id": "knowledge-test",
            "user": 1,
            "organization_id": None,
            "access_level": 1,
            "module_name": "mod",
        }
    ):
        assert know.ingest_document(path="a.pdf")["doc"] == "a.pdf"
        assert know.ingest_document_bytes(filename="a.txt", data=b"x")["bytes"] == "a.txt"

    sdk.session = {"user": {}}
    with pytest.raises(RuntimeError):
        know.ingest_document(path="a.pdf")

    sdk.session = {"user": {"id": 1}}
    with request_context_scope(
        {
            "request_id": "knowledge-test-invalid",
            "user": 1,
            "organization_id": None,
            "access_level": 1,
            "module_name": "mod",
        }
    ):
        with pytest.raises(ValueError, match="path is required"):
            know.ingest_document(path="   ")

        with pytest.raises(ValueError, match="filename is required"):
            know.ingest_document_bytes(filename="  ", data=b"x")
        with pytest.raises(ValueError, match="data must be bytes"):
            know.ingest_document_bytes(filename="a.txt", data="x")

    sdk.extractors = SimpleNamespace(
        extract=lambda **_kwargs: None,
        resolve=lambda **kwargs: {"resolved": kwargs},
    )
    with pytest.raises(RuntimeError, match="registered_extractor_not_found"):
        know.extract_document_data("missing.bin")

    monkeypatch.setattr(knowledge_mod, "app_ctx", lambda: SimpleNamespace(knowledge_ingestion=None))
    with request_context_scope(
        {
            "request_id": "knowledge-test-unavailable",
            "user": 1,
            "organization_id": None,
            "access_level": 1,
            "module_name": "mod",
        }
    ):
        with pytest.raises(RuntimeError, match="knowledge_ingestion_unavailable"):
            know.ingest_document(path="a.pdf")
        with pytest.raises(RuntimeError, match="knowledge_ingestion_unavailable"):
            know.ingest_document_bytes(filename="a.txt", data=b"x")

    monkeypatch.setattr(knowledge_mod, "app_ctx", lambda: SimpleNamespace(knowledge_ingestion=ingestion))
    sdk.session = {"user": {}}
    with request_context_scope(
        {
            "request_id": "knowledge-test-missing-user",
            "user": None,
            "organization_id": None,
            "access_level": 1,
            "module_name": "mod",
        }
    ):
        with pytest.raises(RuntimeError, match="knowledge_ingestion_missing_user_id"):
            know.ingest_document_bytes(filename="a.txt", data=b"x")

    # Engines facade
    monkeypatch.setenv("DEMOCRAI_ENGINE_ORCHESTRATOR", "1")
    eng = engines_mod.Engines()
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.ai.engine.manifests", SimpleNamespace(get_provider_definition=lambda provider_id: {"id": provider_id}, list_provider_definitions=lambda kind=None: [{"kind": kind}]))
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.runtime.dependencies.installer_env", SimpleNamespace(is_engine_supported=lambda engine_id: engine_id == "ok"))

    async def _publish(**kwargs):
        return kwargs

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.ai.engine.install_events", SimpleNamespace(publish_engine_install_requested=_publish))
    runtime_calls = []

    class _EngineRuntime:
        async def sync_active_engines(self):
            runtime_calls.append("sync")

    class _EngineInvocationProvider:
        def sync_active_engines(self):
            runtime_calls.append("sync")

    class _EngineOrchestratorProviderResolver:
        def provider(self):
            return _EngineInvocationProvider()

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.ai.engine.invocation.orchestrator",
        SimpleNamespace(
            EngineOrchestratorProviderResolver=_EngineOrchestratorProviderResolver
        ),
    )
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.ai.engine.runtime", SimpleNamespace(get_engine_runtime=lambda: _EngineRuntime(), check_engine_runtime_config=lambda engine_id, config: {"engine": engine_id, "config": config}))
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.ai.models.catalog", SimpleNamespace(engine_model_source_modes=lambda engine_id: ["catalog"], get_engine_model_management=lambda engine_id: {"m": engine_id}, get_engine_model_schema=lambda engine_id, source_mode: {"schema": source_mode}, list_engine_models=lambda engine_id: [{"id": 1}], resolve_engine_model=lambda *a, **k: {"resolved": True}))
    async def _available_models(engine_id):
        return [{"id": 2, "engine_id": engine_id}]
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.ai.models.instance_models", SimpleNamespace(list_registered_models_for_engine=lambda engine_id: [{"id": 3, "engine_id": engine_id}], list_available_models_for_engine=_available_models))

    assert await eng.get_provider_definition(provider_id="p") == {"id": "p"}
    assert await eng.list_provider_definitions(kind="k") == [{"kind": "k"}]
    assert await eng.is_supported(engine_id="ok") is True
    assert (await eng.request_install(engine_id="e"))["engine_id"] == "e"
    await eng.sync_runtime()
    assert runtime_calls == ["sync"]
    assert (await eng.check_runtime_config(engine_id="e", config={"a": 1}))["engine"] == "e"
    assert await eng.model_source_modes(engine_id="e") == ["catalog"]
    assert (await eng.get_model_management(engine_id="e"))["m"] == "e"
    assert (await eng.get_model_schema(engine_id="e", source_mode="catalog"))["schema"] == "catalog"
    assert await eng.list_models(engine_id="e") == [{"id": 3, "engine_id": "e"}]
    assert await eng.list_available_models(engine_id="e") == [{"id": 2, "engine_id": "e"}]
    assert await eng.list_catalog_models(engine_id="e") == [{"id": 1}]
    assert (await eng.resolve_model(engine_id="e"))["resolved"] is True

    # Effects facade
    broadcast_calls = []
    monkeypatch.setattr(__import__("democrai.core.runtime.foundation.app", fromlist=["x"]), "app_ctx", lambda: SimpleNamespace(network=SimpleNamespace(stream_manager=SimpleNamespace(broadcast=lambda stream_id, data: broadcast_calls.append((stream_id, data)) or contextlib.nullcontext()))))

    class _Builder:
        @staticmethod
        def build_property_update_payload(**kwargs):
            return {"prop": kwargs}

        @staticmethod
        def build_collection_append_payload(**kwargs):
            return {"append": kwargs}

        @staticmethod
        def build_collection_remove_payload(**kwargs):
            return {"remove": kwargs}

        @staticmethod
        def build_collection_replace_payload(**kwargs):
            return {"replace": kwargs}

    sdk.ui = SimpleNamespace(Builder=_Builder)
    eff = effects_mod.Effects(sdk)
    # Publish paths are smoke-tested via helper methods below; direct method returns awaitable from mocked network
    assert eff.navigate("/x")["type"] == "navigate"
    assert eff.render()["type"] == "render"
    assert eff.ui_messages([{"x": 1}])["type"] == "ui_messages"
    assert eff.ui_agent_commands([{"c": 1}])["agentUICommands"]["commands"]
    assert eff.ui_property_update("c", "p", 1)["prop"]["component_id"] == "c"
    assert eff.ui_collection_append("c", "p", 1)["append"]["component_id"] == "c"
    assert eff.ui_collection_remove("c", "p", 1)["remove"]["component_id"] == "c"
    assert eff.ui_collection_replace("c", "p", 1)["replace"]["component_id"] == "c"
    assert eff.pipeline("task", "lbl")["type"] == "pipeline"
    assert eff.confirm()["type"] == "confirm"
    assert eff.notify("ch", {"k": 1})["type"] == "notify"
    assert eff.scroll("c")["component_id"] == "c"
    assert eff.refresh_modules()["type"] == "refresh_modules"
    assert eff.set_jwt("t")["token"] == "t"
    assert eff.copy_to_clipboard("x")["op"] == "copy_to_clipboard"
    assert eff.open_url("https://x")["op"] == "open_url"

    class _Component:
        def to_dict(self):
            return {"component": "x"}

    monkeypatch.setitem(__import__("sys").modules, "democrai.sdk.components.base", SimpleNamespace(Component=_Component))
    out = eff.respond({"a": 1}, "skip", {"c": _Component()}, {"l": [_Component()]})
    assert len(out["effects"]) == 3

    # Models facade
    model_calls = []

    class _Model:
        def __getattr__(self, name):
            return lambda *a, **k: model_calls.append((name, a, k)) or {"name": name}

    monkeypatch.setattr(models_mod, "build_core_model", lambda model_name, ctx: _Model())
    monkeypatch.setattr(models_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False))

    sdk.session = {"user": {"id": 1, "organization_id": 2, "access_level": 3}}
    models_sdk = models_mod.CoreModelsSDK(sdk)
    users = models_sdk.users
    assert users.view(1)["name"] == "view"
    assert users.list(page=1)["name"] == "list"
    assert users.create({"x": 1})["name"] == "create"
    assert users.update(1, {"x": 2})["name"] == "update"
    assert users.delete(1)["name"] == "delete"
    assert users.verify("u", "p")["name"] == "verify"
    assert users.get_info("u")["name"] == "get_info"
    assert users.get_info_by_id(1)["name"] == "get_info_by_id"
    assert users.form_model_create()["name"] == "form_model_create"
    assert users.form_model_update(1)["name"] == "form_model_update"
    assert users.form_model_extra("x")["name"] == "form_model_extra"
    assert users.filters_model()["name"] == "filters_model"
    assert users.table_model()["name"] == "table_model"

    with pytest.raises(PermissionError):
        users._resolve(policy="bypass")

    sdk.session["_models_bypass"] = True
    assert users._resolve(policy="bypass") is not None
    with pytest.raises(AttributeError):
        users.non_existing


@pytest.mark.asyncio
async def test_dependencies_facade_and_effects_async_publish(monkeypatch):
    # Dependencies facade
    ensure_calls = []
    monkeypatch.setattr(
        dependencies_mod,
        "ensure_import",
        lambda module_name, dependency_key=None: ensure_calls.append((module_name, dependency_key)) or {"ok": True},
    )
    dep = dependencies_mod.Dependencies()
    assert dep.ensure_import("pydantic") == {"ok": True}
    assert dep.ensure_import("numpy", dependency_key="num") == {"ok": True}
    assert ensure_calls == [("pydantic", None), ("numpy", "num")]

    # Effects async publish branches
    broadcast_calls = []

    async def _broadcast(stream_id, data):
        broadcast_calls.append((stream_id, data))

    monkeypatch.setattr(
        __import__("democrai.core.runtime.foundation.app", fromlist=["x"]),
        "app_ctx",
        lambda: SimpleNamespace(
            network=SimpleNamespace(stream_manager=SimpleNamespace(broadcast=_broadcast))
        ),
    )

    class _Builder:
        @staticmethod
        def build_property_update_payload(**kwargs):
            return {"prop": kwargs}

        @staticmethod
        def build_collection_append_payload(**kwargs):
            return {"append": kwargs}

        @staticmethod
        def build_collection_remove_payload(**kwargs):
            return {"remove": kwargs}

        @staticmethod
        def build_collection_replace_payload(**kwargs):
            return {"replace": kwargs}

    eff = effects_mod.Effects(SimpleNamespace(ui=SimpleNamespace(Builder=_Builder), module_name="m1"))
    await eff.publish_ui_message("s1", {"type": "ping"})
    await eff.publish_property_update("s1", "c1", "p1", 42)
    await eff.publish_collection_append("s1", "c1", "items", {"x": 1})
    await eff.publish_collection_remove("s1", "c1", "items", {"x": 1})
    await eff.publish_collection_replace("s1", "c1", "items", [{"x": 2}])
    assert len(broadcast_calls) == 5
    assert eff.render("/explicit")["path"] == "/explicit"
    assert eff.pipeline("task", "lbl", args={"x": 1}, module="custom")["module"] == "custom"
    assert eff.confirm(path="/a", params={"x": 1}, render=False)["render"] is False


@pytest.mark.asyncio
async def test_decorator_helpers_and_binding(monkeypatch):
    current_sdk = ContextVar("current_sdk", default=None)
    monkeypatch.setitem(__import__("sys").modules, "democrai.sdk.client", SimpleNamespace(current_sdk=current_sdk))

    registered_actions = {}
    registered_functions = {}
    event_ops = []
    hook_ops = []

    mod = SimpleNamespace(
        _get_module_prefix=lambda func: "mod",
        _event_warning=lambda msg: event_ops.append(("warn", msg)),
        _hook_warning=lambda msg: hook_ops.append(("warn", msg)),
        _get_registry_owner=lambda prefix, name: "owner",
        action_registry=SimpleNamespace(
            register_action=lambda name, fn: registered_actions.setdefault(name, fn),
            register_function=lambda name, fn: registered_functions.setdefault(name, fn),
        ),
        module_event_registry=SimpleNamespace(
            register=lambda *a, **k: event_ops.append(("register", a, k)),
            declare=lambda *a, **k: event_ops.append(("declare", a, k)),
        ),
        render_hook_registry=SimpleNamespace(
            register=lambda *a, **k: hook_ops.append(("register", a, k)),
            declare=lambda *a, **k: hook_ops.append(("declare", a, k)),
        ),
        template_registry=SimpleNamespace(register=lambda *a, **k: hook_ops.append(("template", a, k))),
    )

    @action_helpers_mod.action(mod)
    async def my_action(ctx, session, sdk, value=0):
        return {"ok": sdk.module_name, "value": value, "ctx": ctx}

    assert "mod.my_action" in registered_actions
    out = await registered_actions["mod.my_action"]({"value": 7}, {}, SimpleNamespace(module_name="mod"))
    assert out["value"] == 7

    @action_helpers_mod.function(mod)
    def my_function(x):
        return x + 1

    assert "mod.my_function" in registered_functions
    assert my_function(1) == 2

    @action_helpers_mod.event_listener(mod, name="")
    def bad_listener():
        return None

    @action_helpers_mod.event_listener(mod, name="mod.ev", priority=2)
    def good_listener():
        return None

    @action_helpers_mod.event_slot(mod, name="", params=["a"])
    def bad_slot():
        return None

    @action_helpers_mod.event_slot(mod, name="ev", params=["a", 1, ""], optional=False, description="d")
    def good_slot():
        return None

    assert any(op[0] == "warn" for op in event_ops)
    assert any(op[0] == "register" for op in event_ops)
    assert any(op[0] == "declare" for op in event_ops)

    @ui_helpers_mod.ui_template(mod)
    def tpl():
        return None

    @ui_helpers_mod.render_hook(mod, name="")
    def bad_hook():
        return None

    @ui_helpers_mod.render_hook(mod, name="mod.hook", priority=1)
    def good_hook():
        return None

    @ui_helpers_mod.render_hook_slot(mod, name="", optional=False)
    def bad_hook_slot():
        return None

    @ui_helpers_mod.render_hook_slot(mod, name="slot", optional=False, description="d")
    def good_hook_slot():
        return None

    assert any(op[0] == "template" for op in hook_ops)
    assert any(op[0] == "warn" for op in hook_ops)
    assert any(op[0] == "register" for op in hook_ops)
    assert any(op[0] == "declare" for op in hook_ops)

    # decorator binding
    calls = []

    def _mk_base(name):
        def _base(*args, **kwargs):
            def _decorator(func):
                calls.append((name, args, kwargs, func.__name__))
                return func

            return _decorator

        return _base

    sdk = SimpleNamespace(
        module_name="mod",
        base_action=_mk_base("action"),
        base_callable_command=_mk_base("callable"),
        base_scheduled_command=_mk_base("scheduled"),
        base_long_run_command=_mk_base("long_run"),
        base_single_run_command=_mk_base("single_run"),
        base_function=_mk_base("function"),
        base_tool=_mk_base("tool"),
        base_agent=_mk_base("agent"),
        base_pipeline=_mk_base("pipeline"),
        base_ui_template=_mk_base("ui_template"),
        base_home_page=_mk_base("home"),
        base_guest_page=_mk_base("guest"),
        base_render_hook=_mk_base("render_hook"),
        base_render_hook_slot=_mk_base("render_hook_slot"),
        base_event_listener=_mk_base("event_listener"),
        base_event_slot=_mk_base("event_slot"),
    )

    binding_mod.bind_module_decorators(sdk)

    @sdk.action()
    def a():
        return None

    @sdk.callable_command()
    def b():
        return None

    @sdk.scheduled_command(interval_seconds=1)
    def c():
        return None

    @sdk.long_run_command(restart_on_exit=False)
    def d():
        return None

    @sdk.single_run_command()
    def e():
        return None

    @sdk.function()
    def f():
        return None

    @sdk.tool(description="x")
    def g():
        return None

    @sdk.agent(description="x")
    def h():
        return None

    @sdk.pipeline(description="x")
    def i():
        return None

    @sdk.ui_template()
    def j():
        return None

    @sdk.home_page("/")
    def k():
        return None

    @sdk.guest_page("/g")
    def l():
        return None

    @sdk.render_hook()
    def m():
        return None

    @sdk.render_hook_slot("x")
    def n():
        return None

    @sdk.event_listener()
    def o():
        return None

    @sdk.event_slot("x")
    def p():
        return None

    assert any(c[0] == "action" for c in calls)


@pytest.mark.asyncio
async def test_sdk_action_validation_filters_ctx_and_defaults(monkeypatch):
    current_sdk = ContextVar("current_sdk_validation", default=None)
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.sdk.client",
        SimpleNamespace(current_sdk=current_sdk),
    )

    registered = {}
    mod = SimpleNamespace(
        _get_module_prefix=lambda _func: "mod",
        action_registry=SimpleNamespace(register_action=lambda name, fn: registered.setdefault(name, fn)),
    )

    class Payload(BaseModel):
        target: str = "default-target"
        count: int

    def _validate(func):
        return action_validation_mod.set_action_validation(func, schema=Payload, strip_extra=True)

    @action_helpers_mod.action(mod)
    @_validate
    async def validated_action(ctx, session, sdk):
        return {"ctx": ctx, "session": session, "sdk": sdk.module_name}

    out = await registered["mod.validated_action"](
        {
            "count": "3",
            "extra": "drop",
            "_surface_id": "main",
            "_source_component_id": "btn",
            "stream_id": "stream-1",
            "session_key": "session-1",
        },
        {"s": 1},
        SimpleNamespace(module_name="mod"),
    )

    assert out == {
        "ctx": {
            "target": "default-target",
            "count": 3,
            "_surface_id": "main",
            "_source_component_id": "btn",
            "stream_id": "stream-1",
            "session_key": "session-1",
        },
        "session": {"s": 1},
        "sdk": "mod",
    }


@pytest.mark.asyncio
async def test_sdk_action_validation_error_returns_toast(monkeypatch):
    current_sdk = ContextVar("current_sdk_validation_error", default=None)
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.sdk.client",
        SimpleNamespace(current_sdk=current_sdk),
    )

    logger = _Logger()
    monkeypatch.setattr(action_validation_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    registered = {}
    mod = SimpleNamespace(
        _get_module_prefix=lambda _func: "mod",
        action_registry=SimpleNamespace(register_action=lambda name, fn: registered.setdefault(name, fn)),
    )
    called = False

    class Payload(BaseModel):
        count: int

    class _Effects:
        @staticmethod
        def ui_messages(messages):
            return {"type": "ui_messages", "messages": list(messages)}

        @staticmethod
        def respond(*effects):
            return {"effects": list(effects)}

    def _validate(func):
        return action_validation_mod.set_action_validation(func, schema=Payload, strip_extra=True)

    @action_helpers_mod.action(mod)
    @_validate
    async def validated_action(ctx, session, sdk):
        nonlocal called
        called = True
        return {"ctx": ctx}

    out = await registered["mod.validated_action"](
        {},
        {},
        SimpleNamespace(module_name="mod", effects=_Effects()),
    )

    assert called is False
    toast = out["effects"][0]["messages"][0]["eventNotification"]
    assert toast["kind"] == "toast"
    assert toast["variant"] == "error"
    assert "count" in toast["text"]
    assert logger.warnings


def test_agents_registry_and_utils(monkeypatch, tmp_path):
    # agents registry
    tool_reg = agents_registry_mod.AgentToolRegistry()
    tool_reg.register("b", lambda: None, module_name="m")
    tool_reg.register("a", lambda: None, module_name="n")
    assert [t.name for t in tool_reg.get_all()] == ["a", "b"]
    assert [t.name for t in tool_reg.get_all(module_name="m")] == ["b"]

    agent_reg = agents_registry_mod.AgentRegistry()
    pipeline_reg = agents_registry_mod.PipelineRegistry()

    agent_reg.register(SimpleNamespace(name="z", module_name="m"))
    agent_reg.register(SimpleNamespace(name="a", module_name="n"))
    assert [a.name for a in agent_reg.get_all()] == ["a", "z"]
    assert [a.name for a in agent_reg.get_all(module_name="m")] == ["z"]

    pipeline_reg.register(SimpleNamespace(name="p2", module_name="m"))
    pipeline_reg.register(SimpleNamespace(name="p1", module_name="n"))
    assert [p.name for p in pipeline_reg.get_all()] == ["p1", "p2"]
    assert [p.name for p in pipeline_reg.get_all(module_name="m")] == ["p2"]

    # discovery utils
    logger = _Logger()
    monkeypatch.setattr(discovery_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    pkg_root = tmp_path / "mypkg"
    (pkg_root / "ui" / "nested").mkdir(parents=True)
    (pkg_root / "__init__.py").write_text("", encoding="utf-8")
    (pkg_root / "ui" / "__init__.py").write_text("", encoding="utf-8")
    (pkg_root / "ui" / "main.py").write_text("x=1\n", encoding="utf-8")
    (pkg_root / "ui" / "nested" / "__init__.py").write_text("", encoding="utf-8")
    (pkg_root / "ui" / "nested" / "sub.py").write_text("x=1\n", encoding="utf-8")

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        mods = discovery_mod.discover_submodules("mypkg.ui", recursive=True)
        assert any(name.endswith("main") for name in mods)
        merged = discovery_mod.discover_module_ui_modules("mypkg", str(pkg_root), is_builtin=False)
        assert any(name.endswith("main") for name in merged)
        assert any(name.endswith("nested.sub") for name in merged)
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))

    assert discovery_mod.discover_submodules("missing.pkg", recursive=False) == []

    # system utils
    monkeypatch.setattr(system_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(system_mod.psutil, "virtual_memory", lambda: SimpleNamespace(available=2 * 1024 * 1024, total=8 * 1024 * 1024))
    monkeypatch.setattr(system_mod.sys, "platform", "linux")

    class _NVML:
        def __init__(self):
            self.shutdowns = 0

        def nvmlInit(self):
            return None

        def nvmlDeviceGetCount(self):
            return 1

        def nvmlDeviceGetHandleByIndex(self, idx):
            return idx

        def nvmlDeviceGetMemoryInfo(self, handle):
            return SimpleNamespace(free=3 * 1024 * 1024, total=4 * 1024 * 1024)

        def nvmlShutdown(self):
            self.shutdowns += 1

    nvml = _NVML()
    monkeypatch.setattr(system_mod, "nvml", nvml)

    monitor = system_mod.SystemResourceMonitor()
    assert monitor.get_free_ram_mb() == 2
    assert monitor.get_total_ram_mb() == 8
    assert monitor.get_free_vram_mb() == 3
    assert monitor.get_total_vram_mb() == 4
    assert monitor.get_resources()["has_nvidia_gpu"] is True
    monitor.shutdown()
    assert nvml.shutdowns == 1

    system_mod._resource_monitor = None
    first = system_mod.get_resource_monitor()
    second = system_mod.get_resource_monitor()
    assert first is second
    system_mod.shutdown_resource_monitor()
    assert system_mod._resource_monitor is None


@pytest.mark.asyncio
async def test_sdk_action_binding_and_models_low_branches(monkeypatch):
    current_sdk = ContextVar("current_sdk_low", default=None)
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.sdk.client",
        SimpleNamespace(current_sdk=current_sdk),
    )

    registered = {}
    mod = SimpleNamespace(
        _get_module_prefix=lambda _func: "mod",
        action_registry=SimpleNamespace(register_action=lambda name, fn: registered.setdefault(name, fn)),
    )

    @action_helpers_mod.action(mod)
    async def action_with_default(ctx, session, sdk, explicit=None, defaulted=7):
        return {"explicit": explicit, "defaulted": defaulted, "session": session}

    out = await registered["mod.action_with_default"]({"explicit": 3}, {"s": 1}, SimpleNamespace(module_name="mod"))
    assert out["explicit"] == 3
    assert out["defaulted"] == 7

    @action_helpers_mod.action(mod)
    async def action_passthrough(*args, **kwargs):
        return {"args": args, "kwargs": kwargs}

    out2 = await registered["mod.action_passthrough"]("x", y=1)
    assert out2["args"] == ("x",)
    assert out2["kwargs"] == {"y": 1}

    # decorator binding branches for core + explicit names + non-prefixed ids
    calls = []

    def _mk_base(name):
        def _base(*args, **kwargs):
            def _decorator(func):
                calls.append((name, args, kwargs, func.__name__))
                return func

            return _decorator

        return _base

    sdk = SimpleNamespace(
        module_name="core",
        base_action=_mk_base("action"),
        base_callable_command=_mk_base("callable"),
        base_scheduled_command=_mk_base("scheduled"),
        base_long_run_command=_mk_base("long_run"),
        base_single_run_command=_mk_base("single_run"),
        base_function=_mk_base("function"),
        base_tool=_mk_base("tool"),
        base_agent=_mk_base("agent"),
        base_pipeline=_mk_base("pipeline"),
        base_ui_template=_mk_base("ui_template"),
        base_home_page=_mk_base("home"),
        base_guest_page=_mk_base("guest"),
        base_render_hook=_mk_base("render_hook"),
        base_render_hook_slot=_mk_base("render_hook_slot"),
        base_event_listener=_mk_base("event_listener"),
        base_event_slot=_mk_base("event_slot"),
    )
    binding_mod.bind_module_decorators(sdk)

    @sdk.ui_template("explicit")
    def ui_explicit():
        return None

    @sdk.render_hook("explicit.hook")
    def hook_explicit():
        return None

    @sdk.event_listener("explicit.event")
    def evt_explicit():
        return None

    assert any(item[0] == "ui_template" and item[1] == ("explicit",) for item in calls)
    assert any(item[0] == "render_hook" and item[1] == ("explicit.hook",) for item in calls)
    assert any(item[0] == "event_listener" and item[1] == ("explicit.event",) for item in calls)

    sdk_mod = SimpleNamespace(
        module_name="mod",
        base_action=_mk_base("action_mod"),
        base_callable_command=_mk_base("callable_mod"),
        base_scheduled_command=_mk_base("scheduled_mod"),
        base_long_run_command=_mk_base("long_run_mod"),
        base_single_run_command=_mk_base("single_run_mod"),
        base_function=_mk_base("function_mod"),
        base_tool=_mk_base("tool_mod"),
        base_agent=_mk_base("agent_mod"),
        base_pipeline=_mk_base("pipeline_mod"),
        base_ui_template=_mk_base("ui_template_mod"),
        base_home_page=_mk_base("home_mod"),
        base_guest_page=_mk_base("guest_mod"),
        base_render_hook=_mk_base("render_hook_mod"),
        base_render_hook_slot=_mk_base("render_hook_slot_mod"),
        base_event_listener=_mk_base("event_listener_mod"),
        base_event_slot=_mk_base("event_slot_mod"),
    )
    binding_mod.bind_module_decorators(sdk_mod)

    @sdk_mod.action("mod.named")
    def mod_named():
        return None

    # models branches: count + allowed __getattr__ + invalid model name
    monkeypatch.setattr(models_mod, "build_core_model", lambda _name, _ctx: SimpleNamespace(count=lambda **_k: {"name": "count"}))
    monkeypatch.setattr(models_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False))
    models_sdk = models_mod.CoreModelsSDK(SimpleNamespace(module_name="mod", session={"user": {"id": 1, "organization_id": 2, "access_level": 3}}))
    users = models_sdk.users
    assert users.count(filters={"a": 1})["name"] == "count"
    assert callable(users.__getattr__("list"))
    assert models_sdk.users is users
    with pytest.raises(AttributeError):
        models_sdk.__getattr__(" ")
