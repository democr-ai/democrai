from __future__ import annotations

import os

import clients.qtdesktop.utils.paths as paths_mod


def test_desktop_resolve_resource_uses_desktop_assets(monkeypatch, tmp_path):
    desktop_dir = tmp_path / "desktop"
    assets_dir = desktop_dir / "assets"
    assets_dir.mkdir(parents=True)
    icon_path = assets_dir / "fonts" / "icon.json"
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    icon_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(paths_mod, "get_desktop_dir", lambda: str(desktop_dir))

    assert paths_mod.get_assets_dir() == str(assets_dir)
    assert paths_mod.resolve_resource(None) is None
    assert paths_mod.resolve_resource("http://x") == "http://x"
    assert paths_mod.resolve_resource("ric.inline") == "ric.inline"
    abs_path = os.path.abspath(str(tmp_path / "abs.bin"))
    assert paths_mod.resolve_resource(abs_path) == abs_path
    assert paths_mod.resolve_resource("fonts/icon.json") == str(icon_path.resolve())
    assert paths_mod.resolve_resource("clients/qtdesktop/assets/fonts/icon.json") == str(
        icon_path.resolve()
    )
    assert paths_mod.resolve_resource("missing.png") == "missing.png"
