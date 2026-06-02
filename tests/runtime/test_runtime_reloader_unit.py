from __future__ import annotations

from types import SimpleNamespace


def _ctx(*, module_reloads=None, broadcasts=None):
    class _Bus:
        def broadcast(self, message):
            broadcasts.append(message)

    return SimpleNamespace(
        logger=SimpleNamespace(
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            debug=lambda *a, **k: None,
        ),
        modules=SimpleNamespace(reload_all_modules=lambda: module_reloads.append("reload")),
        network=SimpleNamespace(buses=[_Bus()]),
    )


def test_reloader_module_change_reloads_modules_and_broadcasts(tmp_path):
    from democrai.core.runtime.lifecycle.reloader import DevReloader

    module_reloads = []
    broadcasts = []
    module_root = tmp_path / "modules"
    module_file = module_root / "demo" / "view.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")

    reloader = DevReloader(
        ctx=_ctx(module_reloads=module_reloads, broadcasts=broadcasts),
        module_paths=(str(module_root),),
        engine_paths=(),
        extractor_paths=(),
    )
    reloader._changed_files = {str(module_file)}

    reloader._handle_changes()

    assert module_reloads == ["reload"]
    assert broadcasts == [{"type": "hot_reload"}]


def test_reloader_engine_change_requests_application_restart(tmp_path):
    from democrai.core.runtime.lifecycle.reloader import DevReloader

    restarts = []
    module_reloads = []
    broadcasts = []
    engine_root = tmp_path / "engines"
    engine_file = engine_root / "demo" / "engine.py"
    engine_file.parent.mkdir(parents=True)
    engine_file.write_text("", encoding="utf-8")

    reloader = DevReloader(
        ctx=_ctx(module_reloads=module_reloads, broadcasts=broadcasts),
        module_paths=(),
        engine_paths=(str(engine_root),),
        extractor_paths=(),
        restart_application=lambda: restarts.append("restart"),
    )
    reloader._changed_files = {str(engine_file)}

    reloader._handle_changes()

    assert restarts == ["restart"]
    assert module_reloads == []
    assert broadcasts == []


def test_reloader_extractor_change_requests_application_restart(tmp_path):
    from democrai.core.runtime.lifecycle.reloader import DevReloader

    restarts = []
    module_reloads = []
    broadcasts = []
    extractor_root = tmp_path / "extractors"
    extractor_file = extractor_root / "demo" / "extractor.py"
    extractor_file.parent.mkdir(parents=True)
    extractor_file.write_text("", encoding="utf-8")

    reloader = DevReloader(
        ctx=_ctx(module_reloads=module_reloads, broadcasts=broadcasts),
        module_paths=(),
        engine_paths=(),
        extractor_paths=(str(extractor_root),),
        restart_application=lambda: restarts.append("restart"),
    )
    reloader._changed_files = {str(extractor_file)}

    reloader._handle_changes()

    assert restarts == ["restart"]
    assert module_reloads == []
    assert broadcasts == []


def test_reloader_unwatched_client_path_is_ignored(tmp_path):
    from democrai.core.runtime.lifecycle.reloader import DevReloader

    module_reloads = []
    broadcasts = []
    client_root = tmp_path / "clients" / "qtdesktop"
    asset_file = client_root / "assets" / "style.less"
    asset_file.parent.mkdir(parents=True)
    asset_file.write_text("", encoding="utf-8")

    reloader = DevReloader(
        ctx=_ctx(module_reloads=module_reloads, broadcasts=broadcasts),
        module_paths=(),
        engine_paths=(),
        extractor_paths=(),
    )
    reloader._changed_files = {str(asset_file)}

    reloader._handle_changes()

    assert module_reloads == []
    assert broadcasts == []
