from __future__ import annotations

import asyncio
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace

import pytest

import democrai.core.platform.ui.hooks as ui_hooks_mod
import democrai.core.platform.ui.media_sources as media_sources_mod
from democrai.sdk.components.base import Component
from democrai.sdk.ui import Builder


class _Logger:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def warning(self, msg, channel=None):
        self.warnings.append((msg, channel))

    def error(self, msg, channel=None):
        self.errors.append((msg, channel))


class _Cmp(Component):
    type = "Box"


def test_media_sources_resolution_and_rewrite(tmp_path, monkeypatch):
    user_modules = tmp_path / "user_modules"
    builtin_modules = tmp_path / "builtin_modules"
    module_dir = user_modules / "m"
    engine_dir = tmp_path / "engines" / "e1"
    extractor_dir = tmp_path / "extractors" / "x1"

    (module_dir / "images").mkdir(parents=True)
    engine_dir.mkdir(parents=True)
    extractor_dir.mkdir(parents=True)
    (module_dir / "images" / "a.png").write_bytes(b"x")
    (engine_dir / "e.png").write_bytes(b"x")
    (extractor_dir / "x.png").write_bytes(b"x")

    monkeypatch.setattr(media_sources_mod, "get_runtime_module_dirs", lambda: (str(user_modules), str(builtin_modules)))

    assert media_sources_mod.media_fields_for_component("Image") == ("url",)
    assert media_sources_mod.media_fields_for_component("Unknown") == ()

    assert media_sources_mod.resolve_client_media_source(module_name="m", value="https://example.com/a.png").startswith("/media/proxy?")
    assert media_sources_mod.resolve_client_media_source(module_name="m", value="media/x") == "/media/uploads/by-storage-path?storage_path=media%2Fx"

    rel_engine = media_sources_mod.resolve_client_media_source(module_name="m", value="engines/e1/e.png")
    abs_engine = media_sources_mod.resolve_client_media_source(module_name="m", value=str((engine_dir / "e.png").resolve()))
    assert rel_engine == "/media/engine/e1/e.png"
    assert abs_engine == "/media/engine/e1/e.png"

    rel_extractor = media_sources_mod.resolve_client_media_source(module_name="m", value="extractors/x1/x.png")
    abs_extractor = media_sources_mod.resolve_client_media_source(module_name="m", value=str((extractor_dir / "x.png").resolve()))
    assert rel_extractor == "/media/extractors/x1/x.png"
    assert abs_extractor == "/media/extractors/x1/x.png"

    module_asset = media_sources_mod.resolve_client_media_source(module_name="m", module_path=str(module_dir), value="images/a.png")
    assert module_asset == "/media/modules/m/images/a.png"

    assert media_sources_mod.resolve_client_media_source(module_name="m", value="plain-value") == "plain-value"

    # rewrite builder media props
    c = _Cmp("c1")
    c.type = "Image"
    c.props = {"url": "https://example.com/a.png"}
    b = Builder()
    b.add(c)
    media_sources_mod.rewrite_builder_media_sources(b, module_name="m")
    assert c.props["url"].startswith("/media/proxy?")

    props = {"url": {"literalString": "https://example.com/x.png"}}
    media_sources_mod._rewrite_media_prop(props, "url", module_name="m")
    assert props["url"]["literalString"].startswith("/media/proxy?")

    # module base resolution
    assert media_sources_mod._find_module_base("m", module_path=str(module_dir)) == module_dir
    assert media_sources_mod._find_module_base("", module_path=None) is None


def test_media_sources_additional_branches(tmp_path, monkeypatch):
    user_modules = tmp_path / "user_modules"
    builtin_modules = tmp_path / "builtin_modules"
    module_dir = builtin_modules / "m2"
    (module_dir / "images").mkdir(parents=True)
    (module_dir / "images" / "ok.png").write_bytes(b"x")

    monkeypatch.setattr(media_sources_mod, "get_runtime_module_dirs", lambda: (str(user_modules), str(builtin_modules)))

    # passthrough tokens
    assert media_sources_mod.resolve_client_media_source(module_name="m2", value="data:image/png;base64,abc").startswith("data:")
    assert media_sources_mod.resolve_client_media_source(module_name="m2", value="ric.inline") == "ric.inline"
    assert media_sources_mod.resolve_client_media_source(module_name="m2", value="<svg></svg>") == "<svg></svg>"

    # remote/media/engine/extractor negative branches
    assert media_sources_mod._resolve_remote_source(module_name="m2", value="/media/proxy?x=1") == "/media/proxy?x=1"
    assert media_sources_mod._resolve_remote_source(module_name="m2", value="ftp://x") is None
    assert media_sources_mod._resolve_media_storage_source("x") is None
    assert media_sources_mod._resolve_engine_asset_source("engines/e1") is None
    assert media_sources_mod._resolve_engine_asset_source("engines//x") is None
    assert media_sources_mod._resolve_extractor_asset_source("extractors/x1") is None
    assert media_sources_mod._resolve_extractor_asset_source("extractors//x") is None

    # module asset negative branches
    assert media_sources_mod._module_relative_media_path(module_name="m2", value="../x", module_path=str(module_dir)) is None
    assert media_sources_mod._module_relative_media_path(module_name="m2", value="", module_path=str(module_dir)) is None

    # rewrite builder branches: unknown component, props not dict, missing field, string + literal
    c_unknown = _Cmp("u1")
    c_unknown.type = "Unknown"
    c_unknown.props = {"url": "https://example.com/x.png"}
    c_image_no_props = SimpleNamespace(type="Image", props=None)
    c_image_missing = _Cmp("u2")
    c_image_missing.type = "Image"
    c_image_missing.props = {}
    c_image = _Cmp("u3")
    c_image.type = "Image"
    c_image.props = {"url": "https://example.com/x.png"}
    c_image_literal = _Cmp("u4")
    c_image_literal.type = "Image"
    c_image_literal.props = {"url": {"literalString": "https://example.com/y.png"}}
    b = Builder()
    b._components = [c_unknown, c_image_no_props, c_image_missing, c_image, c_image_literal]
    media_sources_mod.rewrite_builder_media_sources(b, module_name="m2")
    assert c_unknown.props["url"] == "https://example.com/x.png"
    assert c_image.props["url"].startswith("/media/proxy?")
    assert c_image_literal.props["url"]["literalString"].startswith("/media/proxy?")

    # find module base from builtin path
    assert media_sources_mod._find_module_base("m2") == module_dir


def test_media_sources_more_branches(tmp_path, monkeypatch):
    user_modules = tmp_path / "user_modules"
    builtin_modules = tmp_path / "builtin_modules"
    module_dir = user_modules / "m3"
    module_dir.mkdir(parents=True)
    file_inside = module_dir / "a" / "b.png"
    file_inside.parent.mkdir(parents=True)
    file_inside.write_bytes(b"x")
    monkeypatch.setattr(media_sources_mod, "get_runtime_module_dirs", lambda: (str(user_modules), str(builtin_modules)))

    assert media_sources_mod.resolve_client_media_source(module_name="m3", value="") == ""
    props = {"url": {"bind": "x"}}
    media_sources_mod._rewrite_media_prop(props, "url", module_name="m3")
    assert props["url"] == {"bind": "x"}
    assert media_sources_mod._resolve_engine_asset_source("") is None
    assert media_sources_mod._resolve_engine_asset_source(str(tmp_path / "engines" / "x.png")) is None
    assert media_sources_mod._resolve_engine_asset_source(str(tmp_path / "not_engines" / "x.png")) is None
    assert media_sources_mod._resolve_engine_asset_source(str(tmp_path / "engines" / "only_engine")) is None
    assert media_sources_mod._resolve_engine_asset_source("engines/e1/") is None
    assert media_sources_mod._resolve_extractor_asset_source("") is None
    assert media_sources_mod._resolve_extractor_asset_source(str(tmp_path / "extractors" / "x.png")) is None
    assert media_sources_mod._resolve_extractor_asset_source(str(tmp_path / "not_extractors" / "x.png")) is None
    assert media_sources_mod._resolve_extractor_asset_source(str(tmp_path / "extractors" / "only_extractor")) is None
    assert media_sources_mod._resolve_extractor_asset_source("extractors/x1/") is None

    rel = media_sources_mod._module_relative_media_path(module_name="m3", value=str(file_inside))
    assert rel == "a/b.png"
    assert media_sources_mod._module_relative_media_path(module_name="m3", value=str(tmp_path / "outside.png")) is None
    assert media_sources_mod._module_relative_media_path(module_name="m3", value="../escape.png", module_path=str(module_dir)) is None
    assert media_sources_mod._module_relative_media_path(module_name="missing", value="x.png", module_path=None) is None

    assert media_sources_mod._find_module_base("m3", module_path=str(tmp_path / "missing_path")) == module_dir
    assert media_sources_mod._find_module_base("missing", module_path=None) is None


@pytest.mark.asyncio
async def test_ui_hooks_runtime_helpers(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(ui_hooks_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, modules=SimpleNamespace(get_module=lambda name: SimpleNamespace(path="/m", name=name) if name == "mod" else None)))

    ui_hooks_mod._hook_warning("w")
    ui_hooks_mod._hook_error("e")
    assert logger.warnings[-1][0] == "w"
    assert logger.errors[-1][0] == "e"

    current_sdk = ContextVar("current_sdk", default=None)

    class _SDK:
        def __init__(self, module_path, module_name, current_path="", session=None):
            self.module_path = module_path
            self.module_name = module_name

    monkeypatch.setitem(__import__("sys").modules, "democrai.sdk.client", SimpleNamespace(SDK=_SDK, current_sdk=current_sdk))

    reg_core = SimpleNamespace(module_name="core", name="slot", func=lambda params, session, sdk, hook_name=None: [sdk.module_name, hook_name, params.get("x")])
    reg_mod = SimpleNamespace(module_name="mod", name="slot", func=lambda module_sdk, params=None: _Cmp("from_mod"))

    core_sdk = ui_hooks_mod._build_hook_sdk(reg_core, {"current_path": "/x"})
    assert core_sdk.module_name == "core"

    mod_sdk = ui_hooks_mod._build_hook_sdk(reg_mod, {"current_path": "/x"})
    assert mod_sdk.module_name == "mod"

    with pytest.raises(RuntimeError):
        ui_hooks_mod._build_hook_sdk(SimpleNamespace(module_name="missing", name="x"), {})

    out_sync = await ui_hooks_mod._invoke_hook_callback(
        reg_core,
        params={"x": 1},
        session={},
        hook_sdk=core_sdk,
    )
    assert out_sync[0] == "core"

    async def _async_cb(params):
        await asyncio.sleep(0)
        return params

    out_async = await ui_hooks_mod._invoke_hook_callback(
        SimpleNamespace(module_name="mod", name="slot", func=_async_cb),
        params={"a": 1},
        session={},
        hook_sdk=mod_sdk,
    )
    assert out_async["a"] == 1

    out_err = await ui_hooks_mod._invoke_hook_callback(
        SimpleNamespace(module_name="mod", name="slot", func=lambda **_k: (_ for _ in ()).throw(RuntimeError("boom"))),
        params={},
        session={},
        hook_sdk=mod_sdk,
    )
    assert out_err is None

    parent = _Cmp("parent")
    parent.children = ["child"]
    child = _Cmp("child")
    prefixed = ui_hooks_mod._prefix_component_tree_ids(parent, "mod", {"child": child})
    assert prefixed.id == "mod_parent"
    assert isinstance(prefixed.children[0], Component)
    assert prefixed.children[0].id == "mod_child"

    # normalize results
    assert len(ui_hooks_mod._normalize_hook_result(_Cmp("x"), reg_mod)) == 1
    bb = Builder()
    bb.add(_Cmp("r1"))
    from_builder = ui_hooks_mod._normalize_hook_result(bb, reg_mod)
    assert from_builder and from_builder[0].id.startswith("mod_")
    from_list = ui_hooks_mod._normalize_hook_result([_Cmp("a"), _Cmp("b")], reg_mod)
    assert len(from_list) == 2
    assert ui_hooks_mod._normalize_hook_result(None, reg_mod) == []
    with pytest.raises(TypeError):
        ui_hooks_mod._normalize_hook_result(["bad"], reg_mod)
    with pytest.raises(TypeError):
        ui_hooks_mod._normalize_hook_result("bad", reg_mod)

    # resolve hooks
    monkeypatch.setattr(
        ui_hooks_mod,
        "render_hook_registry",
        SimpleNamespace(
            get_definition=lambda name: SimpleNamespace(optional=False) if name == "mod.slot" else None,
            get=lambda name: [reg_mod] if name == "mod.slot" else [],
        ),
    )

    resolved = await ui_hooks_mod.resolve_render_hook_components("mod.slot", params={"k": 1}, session={"current_path": "/"})
    assert len(resolved) == 1

    none_registered = await ui_hooks_mod.resolve_render_hook_components("missing.slot", params={}, session={})
    assert none_registered == []
    assert logger.warnings

    ui_hooks_mod._log_missing_hook_callbacks("x", None)
    ui_hooks_mod._log_missing_hook_callbacks("x", SimpleNamespace(optional=False))
    before = len(logger.warnings)
    ui_hooks_mod._log_missing_hook_callbacks("x", SimpleNamespace(optional=True))
    assert len(logger.warnings) == before


@pytest.mark.asyncio
async def test_ui_hooks_remaining_branches(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(
        ui_hooks_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=logger,
            modules=SimpleNamespace(get_module=lambda _name: None),
        ),
    )

    current_sdk = ContextVar("current_sdk_extra", default=None)

    class _SDK:
        def __init__(self, module_path, module_name, current_path="", session=None):
            self.module_name = module_name

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.sdk.client",
        SimpleNamespace(SDK=_SDK, current_sdk=current_sdk),
    )

    parent = _Cmp("p")
    embedded = _Cmp("c")
    parent.children = [embedded, "raw-child", 7]
    out = ui_hooks_mod._prefix_component_tree_ids(parent, "modx", component_map=None)
    assert out.id == "modx_p"
    assert out.children[0].id == "modx_c"
    assert out.children[1] == "modx_raw-child"
    assert out.children[2] == 7

    reg = SimpleNamespace(
        module_name="core",
        name="slot",
        func=lambda params, unknown="fallback": [params, unknown],
    )
    result = await ui_hooks_mod._invoke_hook_callback(
        reg,
        params={"x": 1},
        session={},
        hook_sdk=SimpleNamespace(module_name="core"),
    )
    assert result[1] == "fallback"

    monkeypatch.setattr(
        ui_hooks_mod,
        "render_hook_registry",
        SimpleNamespace(
            get_definition=lambda _name: SimpleNamespace(optional=False),
            get=lambda _name: [SimpleNamespace(module_name="missing", name="slot", func=lambda **_k: _Cmp("x"))],
        ),
    )
    resolved = await ui_hooks_mod.resolve_render_hook_components("slot", params={}, session={})
    assert resolved == []
    assert logger.errors

    # warning/error helper no-logger branch
    monkeypatch.setattr(ui_hooks_mod, "app_ctx", lambda: SimpleNamespace(logger=None))
    ui_hooks_mod._hook_warning("silent-warning")
    ui_hooks_mod._hook_error("silent-error")
