from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import democrai.sdk.ui as sdk_ui_mod
import democrai.core.platform.ui.render_service as render_service_mod
from democrai.sdk.components.base import Component
from democrai.core.runtime.foundation.exceptions import AccessDeniedError, DependencyMissingError


class _Cmp(Component):
    type = "Box"


class _Logger:
    def __init__(self):
        self.logs = []

    def info(self, msg):
        self.logs.append(("info", msg))

    def warning(self, msg):
        self.logs.append(("warning", msg))

    def error(self, msg):
        self.logs.append(("error", msg))

    def debug(self, msg):
        self.logs.append(("debug", msg))


def test_sdk_ui_builder_methods(monkeypatch):
    b = sdk_ui_mod.Builder()
    c1 = _Cmp("c1")
    c2 = _Cmp("c2")
    c1.children = ["c2"]
    b.add(c1).add(c2)
    assert b.get_component("c1") is c1
    assert [c.id for c in b.get_roots()] == ["c1"]

    b.set_data("/a/b", 1)
    assert b._data_model["a"]["b"] == 1

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.runtime.foundation.registry",
        SimpleNamespace(template_registry=SimpleNamespace(get=lambda name: (lambda session=None: ([{"id": "t1", "component": {"Box": {}}, "children": {"explicitList": []}}], "full")) if name in {"tpl", "full"} else None)),
    )

    b.set_template("tpl", {})
    assert b.template == "tpl"

    b.set_surface("aux", shell_route="/shell")
    assert b.surface_id == "aux"
    assert b.shell_route == "/shell"

    dm = b.build_data_model_update(surface_id="aux")
    assert "dataModelUpdate" in json.loads(dm)

    payload = sdk_ui_mod.Builder.build_data_model_update_payload(surface_id="aux", data={"x": 1})
    assert payload["dataModelUpdate"]["surfaceId"] == "aux"

    surf_payload = b.build_surface_update_payload("aux")
    assert surf_payload[0]["surfaceUpdate"]["surfaceId"] == "aux"
    assert isinstance(b.build_surface_update("aux"), str)

    assert json.loads(sdk_ui_mod.Builder.build_delete_surface("aux"))["deleteSurface"]["surfaceId"] == "aux"

    assert sdk_ui_mod.Builder.build_property_update_payload("c", "p", 1)["propertyUpdate"]["action"] == "set"
    assert sdk_ui_mod.Builder.build_collection_append_payload("c", "p", 1)["propertyUpdate"]["action"] == "append"
    assert sdk_ui_mod.Builder.build_collection_remove_payload("c", "p", 1)["propertyUpdate"]["action"] == "remove"
    assert sdk_ui_mod.Builder.build_collection_replace_payload("c", "p", 1)["propertyUpdate"]["action"] == "replace"

    # fallback to full template
    b2 = sdk_ui_mod.Builder()
    b2.set_template("missing", {})
    assert b2.template_components


def test_sdk_ui_wrappers_and_methods(tmp_path, monkeypatch):
    monkeypatch.setattr(sdk_ui_mod, "resolve_module_resource", lambda base, path: f"{base}/{path}")
    monkeypatch.setattr(sdk_ui_mod, "media_fields_for_component", lambda comp_type: ("url", "source"))
    monkeypatch.setattr(sdk_ui_mod, "resolve_client_media_source", lambda **kwargs: f"proxied:{kwargs['value']}")

    class _Image(_Cmp):
        type = "Image"

        def __init__(self, component_id: str, **kwargs):
            super().__init__(component_id)
            self.props.update(kwargs)

    wrapped = sdk_ui_mod._wrap_component(SimpleNamespace(module_path="/m", module_name="mod"), _Image)
    comp = wrapped("img1", url="a.png", action={"name": "act", "context": {"k": 1}}, params={"x": 1})
    assert comp.props["url"].startswith("proxied:")
    assert comp.props["action"] == {"name": "act", "context": {"k": 1}}
    assert comp.props["params"] == {"x": 1}

    assert sdk_ui_mod._maybe_proxy_external_media_source(
        SimpleNamespace(module_name="mod", module_path="/m"),
        component_cls=_Image,
        field="url",
        value="a.png",
    ).startswith("proxied:")

    sdk = SimpleNamespace(module_name="mod", module_path=str(tmp_path), session={"current_path": "/mod"})
    ui = sdk_ui_mod.UI(sdk)

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.application.routing", SimpleNamespace(Router=SimpleNamespace(resolve=lambda route, session, extra_params=None: {"route": route, "extra": extra_params})))
    assert ui.resolve_route("/x", {})["route"] == "/x"
    assert ui.resolve_resource("a.png").endswith("/a.png")
    assert ui.resolve_media_source("a.png", component_type="Image", field="url").startswith("proxied:")

    monkeypatch.setitem(__import__("sys").modules, "democrai.core.platform.ui.yaml_builder", SimpleNamespace(ui_from_yaml=lambda yaml_content, sdk=None: sdk_ui_mod.Builder()))
    assert isinstance(ui.from_yaml("id: x"), sdk_ui_mod.Builder)

    yaml_file = tmp_path / "page.yaml"
    yaml_file.write_text("id: x\n", encoding="utf-8")
    assert isinstance(ui.load("page"), sdk_ui_mod.Builder)

    builder = sdk_ui_mod.Builder()
    content_id = ui.prepare_shell_surface(builder, surface_id="aux", shell_route="/shell", content_component_id="content")
    assert content_id == "content"

    ui.mount_shell_frame(builder, nav_component_id="nav", content_surface_id="content_surface")
    assert builder.get_component("module_root") is not None

    rule_root = ui.nav_active_path_rule("/mod")
    rule_child = ui.nav_active_path_rule("/mod/page")
    assert rule_root["op"] == "=="
    assert rule_child["operator"] == "OR"


@pytest.mark.asyncio
async def test_sdk_ui_additional_branches_and_profiler(monkeypatch, tmp_path):
    # publish_to_stream: no network and with stream manager
    monkeypatch.setattr(sdk_ui_mod, "app_ctx", lambda: SimpleNamespace(network=None))
    await sdk_ui_mod.publish_to_stream("s1", {"x": 1})

    events = []

    class _StreamManager:
        async def broadcast(self, stream_id, data):
            events.append((stream_id, data))

    monkeypatch.setattr(
        sdk_ui_mod,
        "app_ctx",
        lambda: SimpleNamespace(network=SimpleNamespace(stream_manager=_StreamManager())),
    )
    await sdk_ui_mod.publish_to_stream("s2", {"k": 2})
    assert events == [("s2", {"k": 2})]

    # get_roots nested extraction branches
    class _Complex(Component):
        type = "Complex"

    parent = _Complex("parent")
    child = _Complex("child")
    tab_child = _Complex("tab_child")
    left_child = _Complex("left_child")
    center_child = _Complex("center_child")
    right_child = _Complex("right_child")
    parent.children = [{"id": "child", "children": {"explicitList": ["tab_child"]}}]
    parent.props.update(
        {
            "tabs": [{"id": "tab_child"}],
            "left": [{"id": "left_child"}],
            "center": [{"id": "center_child"}],
            "right": [{"id": "right_child"}],
        }
    )

    b = sdk_ui_mod.Builder()
    b.add(parent).add(child).add(tab_child).add(left_child).add(center_child).add(right_child)
    roots = b.get_roots()
    assert [c.id for c in roots] == ["parent"]
    assert b.get_component("missing") is None

    # set_data overwrite non-dict branch
    b._data_model["a"] = 1
    b.set_data("/a/b", 2)
    assert b._data_model["a"]["b"] == 2
    partial = json.loads(b.build_data_model_update(paths=["/a/b", "/a/c", "/missing"]))["dataModelUpdate"]["data"]
    assert partial["/a/b"] == 2
    assert partial["/a/c"] is None

    # build_* with profiler branches
    class _Profiler:
        def span(self, _name):
            class _Span:
                def __enter__(self): return None
                def __exit__(self, exc_type, exc, tb): return False
            return _Span()

    monkeypatch.setattr(sdk_ui_mod, "current_request_profiler", lambda: _Profiler())
    payload = b.build_surface_update_payload("main")
    assert payload[0]["surfaceUpdate"]["surfaceId"] == "main"
    assert isinstance(b.build_surface_update("main"), str)
    assert isinstance(b.build_property_update("parent", "p", 1), str)

    # set_template fallback runtime error branch
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.runtime.foundation.registry",
        SimpleNamespace(template_registry=SimpleNamespace(get=lambda _name: None)),
    )
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "democrai.sdk.templates":
            raise ImportError("missing templates")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    with pytest.raises(RuntimeError):
        sdk_ui_mod.Builder().set_template("not-found", {})

    # load fallback extensions not found
    sdk = SimpleNamespace(module_name="mod", module_path=str(tmp_path), session={})
    ui = sdk_ui_mod.UI(sdk)
    with pytest.raises(FileNotFoundError):
        ui.load("missing_page")

    # _maybe_proxy: field not media-enabled
    assert sdk_ui_mod._maybe_proxy_external_media_source(
        sdk,
        component_cls=type("C", (), {"type": "Image"}),
        field="icon",
        value="/x.png",
    ) == "/x.png"

    # _wrap_component: action params=None and params non-dict branches
    class _Simple(_Complex):
        def __init__(self, cid, **kwargs):
            super().__init__(cid)
            self.props.update(kwargs)

    monkeypatch.setattr(sdk_ui_mod, "resolve_module_resource", lambda base, path: f"{base}/{path}")
    monkeypatch.setattr(sdk_ui_mod, "media_fields_for_component", lambda _type: ("url",))
    monkeypatch.setattr(sdk_ui_mod, "resolve_client_media_source", lambda **kwargs: f"proxied:{kwargs['value']}")
    wrapped = sdk_ui_mod._wrap_component(sdk, _Simple)
    comp1 = wrapped("c1", action={"name": "go", "context": {"x": 1}}, params=None)
    comp2 = wrapped("c2", action={"name": "go", "context": {"x": 1}}, params=[])
    assert comp1.props["action"] == {"name": "go", "context": {"x": 1}}
    assert comp1.props["params"] is None
    assert comp2.props["action"] == {"name": "go", "context": {"x": 1}}
    assert comp2.props["params"] == []


@pytest.mark.asyncio
async def test_render_service_helper_paths(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(render_service_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False, logger=logger))
    monkeypatch.setattr(render_service_mod, "_debug_ui_trace", lambda *a, **k: None)

    # minimal sdk.ui used by helper methods
    class _UI:
        @staticmethod
        def Column(cid, children):
            c = _Cmp(cid)
            c.children = list(children or [])
            return c

        @staticmethod
        def Dialog(cid, title, children):
            c = _Cmp(cid)
            c.props["title"] = title
            c.children = list(children or [])
            return c

    monkeypatch.setattr(render_service_mod, "sdk", SimpleNamespace(ui=_UI))

    class _SessionService:
        def __init__(self):
            self.persisted = []

        def persist(self, user):
            self.persisted.append(user)

    service = render_service_mod.RenderService(_SessionService())

    assert service._is_subsurface_render(SimpleNamespace(surface_id="aux", shell_route="/shell")) is True
    assert service._get_session_user({"user": {"username": "fab"}}) == "fab"
    assert service._resolve_current_path({"current_path": "/x"}) == "/x"
    monkeypatch.setattr(render_service_mod, "resolve_guest_page_path", lambda: "/auth/login")
    monkeypatch.setattr(render_service_mod, "resolve_home_page_path", lambda: "/auth/profile")
    assert service._resolve_current_path({}) == "/auth/login"
    assert service._resolve_current_path({"current_path": "/"}) == "/auth/login"
    assert service._resolve_current_path({"current_path": "", "user": {"username": "fab"}}) == "/auth/profile"

    monkeypatch.setattr(render_service_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=True, logger=logger))
    assert service._resolve_current_path({}) == "/system/setup"
    monkeypatch.setattr(render_service_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False, logger=logger))

    c = _Cmp("r1")
    b_content = sdk_ui_mod.Builder()
    b_content.add(c)
    b_content.template = "full"
    builder, page_ids = service._build_page_container(b_content, "/x")
    assert page_ids == ["r1"]

    # finalize + response helpers
    monkeypatch.setattr(sdk_ui_mod.Builder, "set_template", lambda self, name, session=None: setattr(self, "template", name) or self)
    service._finalize_layout(builder, page_ids, b_content, {})
    assert builder.get_component("content_area_container") is not None

    render_response = service._build_render_response(builder, "app", "page", {}, extra_messages=[{"deleteSurface": {"surfaceId": "x"}}])
    assert render_response[0]["current_path"]["app_name"] == "app"

    assert service._should_use_persistent_shell(SimpleNamespace(surface_id="main", template="full", shell_route=None))
    assert not service._should_use_persistent_shell(SimpleNamespace(surface_id="aux", template="full", shell_route=None))

    sess = {render_service_mod.RenderService._MAIN_TEMPLATE_SESSION_KEY: "full"}
    assert service._active_main_template(sess) == "full"
    service._store_active_main_template(sess, "window")
    assert sess[render_service_mod.RenderService._MAIN_TEMPLATE_SESSION_KEY] == "window"
    service._store_active_main_template(sess, None)
    assert render_service_mod.RenderService._MAIN_TEMPLATE_SESSION_KEY not in sess

    sess_aux = {"_active_aux_surfaces": ["aux1", "main", "main_content"], "_active_shell_route": "/shell"}
    cleanup = service._cleanup_aux_surfaces(sess_aux)
    assert cleanup == [{"deleteSurface": {"surfaceId": "aux1"}}]

    builder._data_model = {"k": 1}
    assert service._build_data_model_messages(builder, surface_id="main")

    empty_aux = service._build_aux_surface_messages(sdk_ui_mod.Builder(), surface_id="aux")
    assert empty_aux == [{"deleteSurface": {"surfaceId": "aux"}}]

    b_multi = sdk_ui_mod.Builder()
    b_multi.add(_Cmp("a"))
    b_multi.add(_Cmp("b"))
    aux_msgs = service._build_aux_surface_messages(b_multi, surface_id="aux")
    assert any("beginRendering" in item for item in aux_msgs)

    b_window = sdk_ui_mod.Builder()
    b_window.template_dimensions = "window"
    b_window.add(_Cmp("root"))
    surf_msgs = service._build_surface_messages(b_window, surface_id="main", include_window_actions=True)
    assert any("windowAction" in item for item in surf_msgs)

    # main content anchor resolution
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.runtime.foundation.registry",
        SimpleNamespace(
            template_registry=SimpleNamespace(
                get=lambda name: (lambda session=None: ([{"id": "host", "component": {"SurfaceHost": {"tag": "@main_content", "surface_id": "content_x"}}, "children": {"explicitList": []}}], "full")) if name == "x" else None
            )
        ),
    )
    assert service._resolve_main_content_surface_id("x", {}) == "content_x"
    assert service._resolve_main_content_surface_id("missing", {}) == "main_content"

    # append pending modal success and failure
    async def _resolve(path, session, extra_params=None):
        b = sdk_ui_mod.Builder()
        b.add(_Cmp("modal_inner"))
        return b

    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(resolve=_resolve, parse_path=lambda path: ("app", "page", {})))
    monkeypatch.setattr(render_service_mod, "rewrite_builder_media_sources", lambda *a, **k: None)
    session = {"pending_modal": {"path": "/m", "params": {"k": 1}}}
    page_ids = ["r1"]
    await service._append_pending_modal(builder, page_ids, session)
    assert "pending_modal_frame" in page_ids

    async def _resolve_err(path, session, extra_params=None):
        raise RuntimeError("x")

    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(resolve=_resolve_err, parse_path=lambda path: ("app", "page", {})))
    session = {"pending_modal": "/m"}
    await service._append_pending_modal(builder, page_ids, session)
    assert session["pending_modal"] is None


@pytest.mark.asyncio
async def test_render_service_render_main_branches(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(render_service_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False, logger=logger))
    monkeypatch.setattr(render_service_mod, "_debug_ui_trace", lambda *a, **k: None)
    monkeypatch.setattr(render_service_mod, "rewrite_builder_media_sources", lambda *a, **k: None)
    monkeypatch.setattr(render_service_mod, "current_request_profiler", lambda: None)
    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(parse_path=lambda path: ("app", "page", {})))
    monkeypatch.setattr(render_service_mod, "sdk", SimpleNamespace(ui=SimpleNamespace(Column=lambda cid, children: _Cmp(cid))))

    service = render_service_mod.RenderService(SimpleNamespace(persist=lambda user: None))

    async def _content(*_a, **_k):
        b = sdk_ui_mod.Builder()
        b.template = "full"
        b.add(_Cmp("c1"))
        return b

    monkeypatch.setattr(service, "_resolve_content", _content)

    async def _persistent(**kwargs):
        return [{"mode": "persistent"}]

    monkeypatch.setattr(service, "_render_persistent_shell", _persistent)
    monkeypatch.setattr(service, "_should_use_persistent_shell", lambda builder, prev_template=None: True)
    out_persistent = await service.render({"current_path": "/app/page", "user": {"username": "u"}})
    assert out_persistent[0]["mode"] == "persistent"

    async def _subsurface(**kwargs):
        return [{"mode": "subsurface"}]

    monkeypatch.setattr(service, "_should_use_persistent_shell", lambda builder, prev_template=None: False)
    monkeypatch.setattr(service, "_is_subsurface_render", lambda builder: True)
    monkeypatch.setattr(service, "_render_subsurface_response", _subsurface)
    out_subsurface = await service.render({"current_path": "/app/page", "user": {"username": "u"}})
    assert out_subsurface[0]["mode"] == "subsurface"

    monkeypatch.setattr(service, "_is_subsurface_render", lambda builder: False)
    async def _append_modal_noop(*_a, **_k):
        return None

    monkeypatch.setattr(service, "_append_pending_modal", _append_modal_noop)
    monkeypatch.setattr(service, "_finalize_layout", lambda *a, **k: None)
    monkeypatch.setattr(service, "_cleanup_aux_surfaces", lambda session: [])
    monkeypatch.setattr(service, "_build_render_response", lambda *a, **k: [{"mode": "full"}])
    out_full = await service.render({"current_path": "/app/page", "user": {"username": "u"}})
    assert out_full[0]["mode"] == "full"


@pytest.mark.asyncio
async def test_render_service_render_with_profiler_and_resolve_content_errors(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(render_service_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False, logger=logger))
    monkeypatch.setattr(render_service_mod, "_debug_ui_trace", lambda *a, **k: None)
    monkeypatch.setattr(render_service_mod, "rewrite_builder_media_sources", lambda *a, **k: None)
    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(parse_path=lambda path: ("app", "page", {}), resolve=None))
    monkeypatch.setattr(render_service_mod, "sdk", SimpleNamespace(ui=SimpleNamespace(Column=lambda cid, children: _Cmp(cid))))

    class _Profiler:
        def span(self, _name):
            class _Ctx:
                def __enter__(self): return None
                def __exit__(self, exc_type, exc, tb): return False
            return _Ctx()

    monkeypatch.setattr(render_service_mod, "current_request_profiler", lambda: _Profiler())

    service = render_service_mod.RenderService(SimpleNamespace(persist=lambda user: None))

    async def _content(*_a, **_k):
        b = sdk_ui_mod.Builder()
        b.template = "full"
        b.add(_Cmp("c1"))
        return b

    monkeypatch.setattr(service, "_resolve_content", _content)
    monkeypatch.setattr(service, "_should_use_persistent_shell", lambda builder, prev_template=None: True)

    async def _persistent_prof(**kwargs):
        return [{"mode": "persistent-prof"}]

    monkeypatch.setattr(service, "_render_persistent_shell", _persistent_prof)
    out_prof = await service.render({"current_path": "/app/page", "user": {"username": "u"}})
    assert out_prof[0]["mode"] == "persistent-prof"

    # _resolve_content: AccessDenied flow
    redirects = []

    async def _resolve_access(path, session, extra_params=None):
        redirects.append(path)
        if len(redirects) == 1:
            raise AccessDeniedError("denied")
        if len(redirects) == 2:
            return sdk_ui_mod.Builder()
        return sdk_ui_mod.Builder()

    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(resolve=_resolve_access, parse_path=lambda path: ("app", "page", {})))
    monkeypatch.setattr(render_service_mod, "remember_post_login_path", lambda session, current_path: session.__setitem__("post_login", current_path))
    monkeypatch.setattr(render_service_mod, "resolve_guest_page_path", lambda: "/guest")
    monkeypatch.setattr(render_service_mod, "DEFAULT_GUEST_PAGE", "/guest/default")
    ss = SimpleNamespace(persisted=[], persist=lambda user: ss.persisted.append(user))
    service2 = render_service_mod.RenderService(ss)
    out_access = await service2._resolve_content("/private", {"user": {"username": "u"}}, "u")
    assert isinstance(out_access, sdk_ui_mod.Builder)
    assert ss.persisted

    # _resolve_content: dependency missing flow
    async def _resolve_dep(path, session, extra_params=None):
        if not session.get("flag"):
            session["flag"] = True
            raise DependencyMissingError("missing", dependency="pkg", dependency_key="pkg")
        return sdk_ui_mod.Builder()

    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(resolve=_resolve_dep, parse_path=lambda path: ("app", "page", {})))
    session = {}
    out_dep = await service2._resolve_content("/x", session, "u")
    assert isinstance(out_dep, sdk_ui_mod.Builder)
    assert "pending_modal" not in session
    assert session["_pending_toasts"][0]["eventNotification"] == {
        "kind": "toast",
        "variant": "error",
        "title": "Missing dependency",
        "text": "Missing AI dependency: pkg",
    }


@pytest.mark.asyncio
async def test_render_service_subsurface_and_persistent_extra_paths(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(render_service_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False, logger=logger))
    monkeypatch.setattr(render_service_mod, "rewrite_builder_media_sources", lambda *a, **k: None)
    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(parse_path=lambda path: ("app", "page", {"k": 1})))
    monkeypatch.setattr(render_service_mod, "_debug_ui_trace", lambda *a, **k: None)

    class _UI:
        @staticmethod
        def Column(cid, children):
            c = _Cmp(cid)
            c.children = list(children)
            return c

    monkeypatch.setattr(render_service_mod, "sdk", SimpleNamespace(ui=_UI))
    service = render_service_mod.RenderService(SimpleNamespace(persist=lambda _u: None))

    # _render_subsurface_response: shell changed + stale aux cleanup
    content = sdk_ui_mod.Builder()
    content.set_surface("aux_new", shell_route="/shell")
    content.add(_Cmp("aux_root"))
    shell = sdk_ui_mod.Builder()
    shell.template = "full"
    shell.add(_Cmp("shell_root"))

    async def _resolve_content(path, session, user):
        assert path == "/shell"
        return shell

    monkeypatch.setattr(service, "_resolve_content", _resolve_content)
    monkeypatch.setattr(service, "_build_surface_messages", lambda *a, **k: [{"surface": "main"}])
    monkeypatch.setattr(service, "_build_aux_surface_messages", lambda *a, **k: [{"surface": "aux"}])
    monkeypatch.setattr(service, "_append_pending_modal", lambda *a, **k: __import__("asyncio").sleep(0))
    monkeypatch.setattr(service, "_finalize_layout", lambda *a, **k: None)

    session = {"_active_shell_route": "/old", "_active_aux_surfaces": ["aux_old", "aux_new"], "active_app_name": "x"}
    out = await service._render_subsurface_response(
        session=session,
        user="u",
        current_path="/app/page",
        content_builder=content,
        app_name="app",
        page_path="page",
        params={"k": 1},
    )
    assert out[0]["current_path"]["app_name"] == "app"
    assert {"deleteSurface": {"surfaceId": "aux_old"}} in out
    assert session["_active_shell_route"] == "/shell"
    assert session["_active_aux_surfaces"] == ["aux_new"]
    assert "active_app_name" not in session

    # _render_persistent_shell: template change + modal error branch + modal close branch
    content2 = sdk_ui_mod.Builder()
    content2.template = "full"
    content2.add(_Cmp("content_root"))
    session2 = {
        render_service_mod.RenderService._MAIN_TEMPLATE_SESSION_KEY: "window",
        "pending_modal": {"path": "/modal/path", "params": {"x": 1}},
        "_pending_modal_active": True,
        "_active_aux_surfaces": ["aux_x"],
    }
    monkeypatch.setattr(service, "_cleanup_aux_surfaces", lambda _s: [{"deleteSurface": {"surfaceId": "aux_x"}}])
    monkeypatch.setattr(service, "_resolve_main_content_surface_id", lambda tpl, _s: "content_sid")
    monkeypatch.setattr(service, "_build_surface_messages", lambda *a, **k: [{"main_shell": True}])
    monkeypatch.setattr(service, "_build_aux_surface_messages", lambda *a, **k: [{"aux_surface": True}])

    async def _resolve_modal_fail(path, session, extra_params=None):
        raise RuntimeError("modal boom")

    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(parse_path=lambda path: ("app", "p", {}), resolve=_resolve_modal_fail))

    out2 = await service._render_persistent_shell(
        session=session2,
        user="u",
        current_path="/app/page",
        content_builder=content2,
        force_refresh=False,
    )
    assert {"deleteSurface": {"surfaceId": "content_sid"}} in out2
    assert {"deleteSurface": {"surfaceId": "modal"}} in out2
    assert session2["pending_modal"] is None
    assert session2["active_app_name"] == "app"

    # pending modal close when no pending but active flag exists
    session3 = {
        render_service_mod.RenderService._MAIN_TEMPLATE_SESSION_KEY: "full",
        "_pending_modal_active": True,
    }
    out3 = await service._render_persistent_shell(
        session=session3,
        user="u",
        current_path="/app/page",
        content_builder=content2,
        force_refresh=False,
    )
    assert {"deleteSurface": {"surfaceId": "modal"}} in out3


@pytest.mark.asyncio
async def test_render_service_resolve_content_fallbacks_and_profiler_non_persistent(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(render_service_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False, logger=logger))
    monkeypatch.setattr(render_service_mod, "rewrite_builder_media_sources", lambda *a, **k: None)
    monkeypatch.setattr(render_service_mod, "_debug_ui_trace", lambda *a, **k: None)
    monkeypatch.setattr(render_service_mod, "sdk", SimpleNamespace(ui=SimpleNamespace(Column=lambda cid, children: _Cmp(cid))))

    class _Profiler:
        def span(self, _name):
            class _Span:
                def __enter__(self): return None
                def __exit__(self, exc_type, exc, tb): return False
            return _Span()

    monkeypatch.setattr(render_service_mod, "current_request_profiler", lambda: _Profiler())
    service = render_service_mod.RenderService(SimpleNamespace(persist=lambda _u: None))

    # _resolve_content: access denied twice then default guest fallback
    calls = {"count": 0}

    async def _resolve_access(path, session, extra_params=None):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise AccessDeniedError("denied")
        b = sdk_ui_mod.Builder()
        b.add(_Cmp("ok"))
        return b

    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(resolve=_resolve_access, parse_path=lambda path: ("app", "page", {})))
    monkeypatch.setattr(render_service_mod, "resolve_guest_page_path", lambda: "/guest/private")
    monkeypatch.setattr(render_service_mod, "DEFAULT_GUEST_PAGE", "/guest/default")
    monkeypatch.setattr(render_service_mod, "remember_post_login_path", lambda session, path: session.__setitem__("post_login", path))
    ss = SimpleNamespace(saved=[], persist=lambda user: ss.saved.append(user))
    service2 = render_service_mod.RenderService(ss)
    sess = {"user": {"username": "u"}}
    out = await service2._resolve_content("/private", sess, "u")
    assert isinstance(out, sdk_ui_mod.Builder)
    assert sess["current_path"] == "/guest/default"
    assert len(ss.saved) == 2

    # _resolve_content: non dependency error is re-raised
    async def _resolve_runtime_error(path, session, extra_params=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(resolve=_resolve_runtime_error, parse_path=lambda path: ("app", "page", {})))
    with pytest.raises(RuntimeError):
        await service2._resolve_content("/x", {}, "u")

    # render with profiler, non-persistent, non-subsurface path
    async def _resolve_builder(*_a, **_k):
        b = sdk_ui_mod.Builder()
        b.template = "full"
        b.add(_Cmp("main_root"))
        return b

    monkeypatch.setattr(service, "_resolve_content", _resolve_builder)
    monkeypatch.setattr(service, "_should_use_persistent_shell", lambda *a, **k: False)
    monkeypatch.setattr(service, "_is_subsurface_render", lambda *a, **k: False)
    monkeypatch.setattr(service, "_append_pending_modal", lambda *a, **k: __import__("asyncio").sleep(0))
    monkeypatch.setattr(service, "_finalize_layout", lambda *a, **k: None)
    monkeypatch.setattr(service, "_cleanup_aux_surfaces", lambda _s: [])
    monkeypatch.setattr(service, "_build_render_response", lambda *a, **k: [{"mode": "profile-full"}])
    monkeypatch.setattr(service, "_active_main_template", lambda _s: "legacy")
    monkeypatch.setattr(service, "_resolve_main_content_surface_id", lambda *_a, **_k: "main_content")
    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(parse_path=lambda path: ("app", "page", {}), resolve=_resolve_builder))

    out_render = await service.render({"current_path": "/app/page", "user": {"username": "u"}})
    assert out_render == [{"mode": "profile-full"}]


def test_render_service_misc_small_branches(monkeypatch):
    # _module_name_for_path fallback
    monkeypatch.setattr(render_service_mod, "Router", SimpleNamespace(parse_path=lambda path: ("", "", {})))
    assert render_service_mod.RenderService._module_name_for_path("") == "dashboard"

    # _build_surface_messages without window actions
    service = render_service_mod.RenderService(SimpleNamespace(persist=lambda _u: None))
    b = sdk_ui_mod.Builder()
    b.add(_Cmp("root"))
    messages = service._build_surface_messages(b, surface_id="aux", include_window_actions=False)
    assert all("windowAction" not in msg for msg in messages)

    # _build_aux_surface_messages single root path
    b_single = sdk_ui_mod.Builder()
    b_single.add(_Cmp("single"))
    aux = service._build_aux_surface_messages(b_single, surface_id="aux")
    assert aux[-1]["beginRendering"]["root"] == "single"

    # _resolve_main_content_surface_id fallback to component id and exception fallback
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.runtime.foundation.registry",
        SimpleNamespace(
            template_registry=SimpleNamespace(
                get=lambda name: (lambda session=None: ([{"id": "cid", "component": {"SurfaceHost": {"tag": "@main_content"}}}], "full")) if name == "cid" else (lambda session=None: (_ for _ in ()).throw(RuntimeError("x")))
            )
        ),
    )
    assert service._resolve_main_content_surface_id("cid", {}) == "cid"
    assert service._resolve_main_content_surface_id("err", {}) == "main_content"
