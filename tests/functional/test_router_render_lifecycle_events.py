from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import democrai.core.application.auth.service as auth_service_mod
from democrai.core.application.handler.action_resolution import invalidate_legacy_action_cache
from democrai.core.application.handler.action_resolution import resolve_legacy_action
from democrai.core.application.routing import Router
import democrai.core.application.routing.router_resolution as router_resolution_mod
from democrai.core.infrastructure.database.models import Base as AuthBase
from democrai.core.infrastructure.modules.manager import ModuleManager
from democrai.core.infrastructure.modules.runtime import get_module_runtime
from democrai.sdk.client import SDK as ModuleSDK
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.exceptions import AccessDeniedError
from democrai.core.runtime.foundation.registry import module_event_registry


def _silent_logger() -> SimpleNamespace:
    return SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )


@pytest.fixture()
def isolated_modules_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = app_ctx()
    previous_modules = ctx.modules
    previous_logger = getattr(ctx, "logger", None)
    previous_setup_mode = getattr(ctx, "setup_mode", False)
    previous_module_runtime = getattr(ctx, "module_runtime", None)
    previous_db = getattr(ctx, "db", None)

    listeners_prev = dict(module_event_registry._listeners)  # pylint: disable=protected-access
    definitions_prev = dict(module_event_registry._definitions)  # pylint: disable=protected-access
    order_prev = module_event_registry._registration_order  # pylint: disable=protected-access

    manager = ModuleManager()
    engine = create_engine(f"sqlite:///{tmp_path / 'router-auth.sqlite'}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    AuthBase.metadata.create_all(engine)
    monkeypatch.setattr(auth_service_mod, "SessionLocal", SessionLocal)
    ctx.modules = manager
    ctx.logger = _silent_logger()
    ctx.setup_mode = False
    ctx.module_runtime = None
    ctx.db = SimpleNamespace(get_session=lambda: SessionLocal())
    invalidate_legacy_action_cache()

    try:
        yield manager
    finally:
        invalidate_legacy_action_cache()
        module_event_registry._listeners = listeners_prev  # pylint: disable=protected-access
        module_event_registry._definitions = definitions_prev  # pylint: disable=protected-access
        module_event_registry._registration_order = order_prev  # pylint: disable=protected-access
        ctx.modules = previous_modules
        ctx.logger = previous_logger
        ctx.setup_mode = previous_setup_mode
        ctx.module_runtime = previous_module_runtime
        ctx.db = previous_db
        engine.dispose()


def _register_repo_module(manager: ModuleManager, module_name: str) -> None:
    path = Path.cwd() / "modules" / module_name
    manager._try_register_module(str(path), is_builtin=True, load_ui=True)  # pylint: disable=protected-access
    mod = manager.get_module(module_name)
    assert mod is not None and mod.is_active, f"failed to register module {module_name}"


@pytest.mark.asyncio
async def test_router_reserved_stream_params_come_only_from_request_context(monkeypatch):
    captured: dict = {}

    class _Builder:
        def get_roots(self):
            return []

        def build_surface_update_payload(self, _surface_id):
            return []

    page_module = ModuleType("modules.testrouter.ui.index")

    def render(params, session):
        captured["params"] = params
        captured["session"] = session
        return _Builder()

    page_module.render = render

    monkeypatch.setitem(sys.modules, "modules", ModuleType("modules"))
    monkeypatch.setitem(sys.modules, "modules.testrouter", ModuleType("modules.testrouter"))
    monkeypatch.setitem(sys.modules, "modules.testrouter.ui", ModuleType("modules.testrouter.ui"))
    monkeypatch.setitem(sys.modules, "modules.testrouter.ui.index", page_module)

    monkeypatch.setattr(router_resolution_mod, "_ensure_module_import_paths", lambda _ctx: None)
    monkeypatch.setattr(router_resolution_mod, "is_module_locked_for_session", lambda *_a, **_k: False)
    monkeypatch.setattr(
        router_resolution_mod,
        "req_ctx",
        lambda: SimpleNamespace(
            request_id="runtime:testrouter",
            stream_id="authorized-stream",
        ),
    )

    module = SimpleNamespace(name="testrouter", path="", is_builtin=True)
    ctx = SimpleNamespace(
        logger=_silent_logger(),
        modules=SimpleNamespace(get_module=lambda name: module if name == "testrouter" else None),
    )
    monkeypatch.setattr(router_resolution_mod, "app_ctx", lambda: ctx)

    from democrai.core.application.routing import router as router_mod

    monkeypatch.setattr(
        router_mod.Router,
        "parse_path",
        staticmethod(
            lambda _path: (
                "testrouter",
                "index",
                {
                    "stream_id": "query-stream",
                    "tab": "overview",
                },
            )
        ),
    )
    monkeypatch.setattr(router_mod.Router, "_ensure_module_routes", staticmethod(lambda _module: None))
    monkeypatch.setattr(
        router_mod.ROUTER,
        "match",
        lambda _path: SimpleNamespace(pattern="testrouter/ui/index", params={}),
    )

    session = {
        "user": {
            "id": 1,
            "username": "functional-admin",
            "role": "super",
        },
    }
    await Router.resolve(
        "/testrouter/index?stream_id=query-stream",
        session=session,
        extra_params={
            "stream_id": "extra-stream",
            "modal": "yes",
        },
    )

    assert captured["params"] == {
        "tab": "overview",
        "modal": "yes",
        "stream_id": "authorized-stream",
        "route_params": {},
    }


@pytest.mark.asyncio
async def test_functional_router_resolution_end_to_end(isolated_modules_state: ModuleManager):
    _register_repo_module(isolated_modules_state, "components")

    path = "/components/index?tab=overview"
    app_name, page_path, params = Router.parse_path(path)
    assert app_name == "components"
    assert page_path == "index"
    assert params == {"tab": "overview"}

    with pytest.raises(AccessDeniedError):
        await Router.resolve(path, session={})

    session = {
        "current_path": path,
        "user": {
            "id": 1,
            "username": "functional-admin",
            "role": "super",
            "access_level": 1,
            "organization_id": 1,
        },
    }
    builder = await Router.resolve(path, session=session)
    assert builder is not None
    assert builder.get_roots()


@pytest.mark.asyncio
async def test_functional_sdui_render_pipeline_outputs_valid_tree(isolated_modules_state: ModuleManager):
    _register_repo_module(isolated_modules_state, "components")
    module = isolated_modules_state.get_module("components")
    assert module is not None

    session = {
        "current_path": "/components/index",
        "user": {
            "id": 7,
            "username": "functional-user",
            "role": "super",
            "access_level": 1,
            "organization_id": 1,
        },
    }
    builder = await get_module_runtime().invoke(
        module=module,
        operation="render",
        payload={
            "page_module": "modules.components.ui.index",
            "current_path": "/components/index",
            "params": {},
            "session": dict(session),
        },
        session=dict(session),
        metadata={"mode": "module_render"},
        persistent=False,
    )

    roots = builder.get_roots()
    assert roots, "render must produce at least one root component"

    for component in roots:
        data = component.to_dict()
        inner = data.get("component")
        assert isinstance(inner, dict) and inner
        comp_type = next(iter(inner.keys()))
        props = inner.get(comp_type)
        assert isinstance(comp_type, str) and comp_type.strip()
        json.dumps(props)

    payload = builder.build_surface_update_payload("main")
    json.dumps(payload)
    assert payload and "surfaceUpdate" in payload[0]


def test_functional_module_lifecycle_load_unload_reload(isolated_modules_state: ModuleManager, tmp_path: Path):
    module_name = "functionallifecycle"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "from democrai.sdk.decorators import action",
                "",
                '@action("functional_lifecycle_ping")',
                "async def lifecycle_ping(ctx, session, module_sdk):",
                "    return {'ok': True, 'ctx': dict(ctx or {})}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": module_name,
                "label": "Functional Lifecycle Module",
                "version": "1.0.0",
                "enabled": True,
                "allowed_imports": ["sdk"],
            }
        ),
        encoding="utf-8",
    )

    isolated_modules_state._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = isolated_modules_state.get_module(module_name)
    assert loaded is not None and loaded.is_active

    resolved = resolve_legacy_action("lifecycle_ping", session={})
    assert resolved is not None

    loaded.stop()
    isolated_modules_state._modules.pop(module_name, None)  # pylint: disable=protected-access
    invalidate_legacy_action_cache()
    assert resolve_legacy_action("lifecycle_ping", session={}) is None

    isolated_modules_state._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    reloaded = isolated_modules_state.get_module(module_name)
    assert reloaded is not None and reloaded.is_active
    invalidate_legacy_action_cache()
    assert resolve_legacy_action("lifecycle_ping", session={}) is not None

    for key in list(sys.modules.keys()):
        if key == module_name or key.startswith(f"{module_name}."):
            sys.modules.pop(key, None)


@pytest.mark.asyncio
async def test_functional_event_system_round_trip(isolated_modules_state: ModuleManager, tmp_path: Path):
    module_name = "functionalevent"
    event_name = f"{module_name}.roundtrip"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "from democrai.sdk.decorators import event_listener",
                "",
                '@event_listener("' + event_name + '")',
                "async def on_roundtrip(payload, event_name, module_sdk):",
                "    return {'event': event_name, 'payload': dict(payload or {}), 'module': module_sdk.module_name}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": module_name,
                "label": "Functional Event Module",
                "version": "1.0.0",
                "enabled": True,
                "allowed_imports": ["sdk"],
            }
        ),
        encoding="utf-8",
    )

    isolated_modules_state._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = isolated_modules_state.get_module(module_name)
    assert loaded is not None and loaded.is_active

    sdk = ModuleSDK(
        module_path=loaded.path,
        module_name=loaded.name,
        current_path=f"/{module_name}/index",
        session={
            "current_path": f"/{module_name}/index",
            "user": {"id": 11, "username": "evt", "role": "super", "access_level": 1},
        },
    )
    results = await sdk.events.emit(
        "roundtrip",
        payload={"id": 99, "kind": "functional"},
        session={
            "current_path": f"/{module_name}/index",
            "user": {"id": 11, "username": "evt", "role": "super", "access_level": 1},
        },
    )

    assert results
    assert results[0]["event"] == event_name
    assert results[0]["payload"] == {"id": 99, "kind": "functional"}
