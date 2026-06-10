from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from types import SimpleNamespace

import democrai.core.platform.utils.conditions as conditions_mod
import democrai.core.platform.utils.mime_detection as mime_mod


def test_mime_detection_helpers_and_fallback_paths(monkeypatch):
    monkeypatch.setattr(mime_mod, "_detect_with_libmagic", lambda payload: "")
    monkeypatch.setattr(mime_mod, "_detect_with_filetype", lambda payload: "")

    svg = mime_mod.detect_mime_type(data=b"<svg></svg>", filename=None, declared_content_type=None)
    assert svg.mime_type == "image/svg+xml"
    assert svg.source == "svg_sniff"

    guessed = mime_mod.detect_mime_type(
        data=b"demo",
        filename="photo.jpg",
        declared_content_type=None,
    )
    assert guessed.mime_type == "image/jpeg"
    assert guessed.source == "filename"

    declared = mime_mod.detect_mime_type(
        data=b"demo",
        filename=None,
        declared_content_type="video/mp4; charset=utf-8",
    )
    assert declared.mime_type == "video/mp4"
    assert declared.source == "declared"

    defaulted = mime_mod.detect_mime_type(data=b"", filename=None, declared_content_type=None)
    assert defaulted.mime_type == "application/octet-stream"
    assert defaulted.source == "default"

    monkeypatch.setattr(mime_mod, "_detect_with_libmagic", lambda payload: "application/pdf")
    libmagic = mime_mod.detect_mime_type(data=b"pdf", filename=None, declared_content_type=None)
    assert libmagic.source == "libmagic"

    monkeypatch.setattr(mime_mod, "_detect_with_libmagic", lambda payload: "")
    monkeypatch.setattr(mime_mod, "_detect_with_filetype", lambda payload: "video/mp4")
    filetype = mime_mod.detect_mime_type(data=b"video", filename=None, declared_content_type=None)
    assert filetype.source == "filetype"

    assert mime_mod.extension_for_mime_type("application/json") == ".json"
    assert mime_mod.extension_for_mime_type("video/mp4") == ".mp4"
    assert mime_mod.extension_for_mime_type(None) == ""
    assert mime_mod.filename_hint_from_url("https://example.invalid/path/to/file.txt?x=1") == "file.txt"
    assert mime_mod._normalize_content_type(" Text/Plain ; charset=utf-8 ") == "text/plain"
    assert mime_mod._guess_from_filename("report.md") == "text/markdown"
    assert mime_mod._looks_like_svg(b"\xef\xbb\xbf   <svg></svg>") is True
    assert mime_mod._looks_like_svg(b"<?xml version='1.0'?><svg></svg>") is True
    assert mime_mod._looks_like_svg(b"plain") is False


def test_mime_detection_magic_runtime_paths(monkeypatch, tmp_path):
    original_prepare = mime_mod._prepare_libmagic_runtime
    original_activate = mime_mod._activate_dynamic_library_path
    original_preload = mime_mod._preload_libmagic_library
    monkeypatch.setattr(mime_mod, "_MAGIC_INSTANCE", None)
    monkeypatch.setattr(mime_mod, "_MAGIC_UNAVAILABLE", False)

    class _MagicImpl:
        def __init__(self, mime=True, magic_file=None):
            self.magic_file = magic_file

        def from_buffer(self, payload):
            return "text/plain; charset=utf-8"

    sys.modules["magic"] = SimpleNamespace(Magic=_MagicImpl)
    monkeypatch.setattr(mime_mod, "_prepare_libmagic_runtime", lambda: str(tmp_path / "magic.mgc"))
    instance = mime_mod._get_magic_instance()
    assert instance is mime_mod._get_magic_instance()
    assert mime_mod._detect_with_libmagic(b"hello") == "text/plain"

    monkeypatch.setattr(mime_mod, "_MAGIC_INSTANCE", None)
    monkeypatch.setattr(mime_mod, "_MAGIC_UNAVAILABLE", False)
    sys.modules.pop("magic", None)
    assert mime_mod._get_magic_instance() is None
    assert mime_mod._MAGIC_UNAVAILABLE is True
    monkeypatch.setattr(mime_mod, "_prepare_libmagic_runtime", original_prepare)

    bundled = tmp_path / "third_party" / "libmagic" / "linux"
    bundled.mkdir(parents=True)
    (bundled / "magic.mgc").write_text("demo", encoding="utf-8")
    monkeypatch.setattr(mime_mod, "get_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "linux")
    preload_calls = []
    monkeypatch.setattr(mime_mod, "_activate_dynamic_library_path", lambda path: preload_calls.append(("dll", path)))
    monkeypatch.setattr(mime_mod, "_preload_libmagic_library", lambda path: preload_calls.append(("preload", path)))
    assert mime_mod._bundled_libmagic_dir() == bundled
    assert mime_mod._prepare_libmagic_runtime() == str(bundled / "magic.mgc")
    assert preload_calls[-1] == ("preload", bundled)

    monkeypatch.setattr(mime_mod, "_activate_dynamic_library_path", original_activate)
    monkeypatch.setattr(mime_mod, "_preload_libmagic_library", original_preload)
    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "windows")
    added = []
    monkeypatch.setattr(mime_mod.os, "add_dll_directory", lambda path: added.append(path), raising=False)
    mime_mod._activate_dynamic_library_path(tmp_path)
    assert added == [str(tmp_path)]

    calls = []
    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "linux")
    monkeypatch.setattr(mime_mod, "_candidate_library_names", lambda: ("libmagic.so",))
    monkeypatch.setattr(ctypes, "CDLL", lambda path, mode=None: calls.append((path, mode)))
    lib = tmp_path / "libmagic.so"
    lib.write_text("bin", encoding="utf-8")
    mime_mod._preload_libmagic_library(tmp_path)
    assert calls


def test_mime_detection_low_level_error_and_platform_branches(monkeypatch, tmp_path):
    original_get_magic = mime_mod._get_magic_instance
    original_prepare = mime_mod._prepare_libmagic_runtime
    original_platform_tag = mime_mod._platform_tag
    assert mime_mod._detect_with_filetype(b"") == ""
    sys.modules.pop("filetype", None)
    assert mime_mod._detect_with_filetype(b"data") == ""

    class _Filetype:
        @staticmethod
        def guess(_payload):
            raise RuntimeError("boom")

    sys.modules["filetype"] = _Filetype()
    assert mime_mod._detect_with_filetype(b"data") == ""

    class _FiletypeNone:
        @staticmethod
        def guess(_payload):
            return None

    sys.modules["filetype"] = _FiletypeNone()
    assert mime_mod._detect_with_filetype(b"data") == ""

    class _FiletypeMime:
        @staticmethod
        def guess(_payload):
            return SimpleNamespace(mime="application/json; charset=utf-8")

    sys.modules["filetype"] = _FiletypeMime()
    assert mime_mod._detect_with_filetype(b"data") == "application/json"
    sys.modules.pop("filetype", None)

    monkeypatch.setattr(mime_mod, "_get_magic_instance", lambda: None)
    assert mime_mod._detect_with_libmagic(b"data") == ""

    class _Detector:
        def from_buffer(self, payload):
            raise RuntimeError("boom")

    monkeypatch.setattr(mime_mod, "_get_magic_instance", lambda: _Detector())
    assert mime_mod._detect_with_libmagic(b"data") == ""
    assert mime_mod._detect_with_libmagic(b"") == ""

    monkeypatch.setattr(mime_mod, "_get_magic_instance", original_get_magic)
    monkeypatch.setattr(mime_mod, "_MAGIC_UNAVAILABLE", True)
    assert mime_mod._get_magic_instance() is None
    monkeypatch.setattr(mime_mod, "_MAGIC_UNAVAILABLE", False)
    monkeypatch.setattr(mime_mod, "_MAGIC_INSTANCE", object())
    assert mime_mod._get_magic_instance() is mime_mod._MAGIC_INSTANCE
    monkeypatch.setattr(mime_mod, "_MAGIC_INSTANCE", None)

    class _BadMagic:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("init boom")

    sys.modules["magic"] = SimpleNamespace(Magic=_BadMagic)
    monkeypatch.setattr(mime_mod, "_prepare_libmagic_runtime", lambda: None)
    monkeypatch.setattr(mime_mod, "_MAGIC_UNAVAILABLE", False)
    assert mime_mod._get_magic_instance() is None
    assert mime_mod._MAGIC_UNAVAILABLE is True
    sys.modules.pop("magic", None)

    monkeypatch.setattr(mime_mod, "_prepare_libmagic_runtime", original_prepare)
    monkeypatch.setattr(mime_mod, "_bundled_libmagic_dir", lambda: None)
    monkeypatch.setattr(mime_mod.os, "getenv", lambda key, default="": "/tmp/magic.mgc" if key == "MAGIC" else default)
    assert mime_mod._prepare_libmagic_runtime() == "/tmp/magic.mgc"

    monkeypatch.setattr(mime_mod, "get_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "linux")
    assert mime_mod._bundled_libmagic_dir() is None

    monkeypatch.setattr(mime_mod, "_platform_tag", original_platform_tag)
    monkeypatch.setattr(mime_mod.sys, "platform", "win32")
    assert mime_mod._platform_tag() == "windows"
    monkeypatch.setattr(mime_mod.sys, "platform", "darwin")
    assert mime_mod._platform_tag() == "macos"
    monkeypatch.setattr(mime_mod.sys, "platform", "linux")
    assert mime_mod._platform_tag() == "linux"

    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "windows")
    assert mime_mod._candidate_library_names()[0] == "magic1.dll"
    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "macos")
    assert mime_mod._candidate_library_names()[0] == "libmagic.dylib"
    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "linux")
    assert mime_mod._candidate_library_names()[0] == "libmagic.so.1"

    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "linux")
    mime_mod._activate_dynamic_library_path(tmp_path)
    monkeypatch.setattr(mime_mod, "_platform_tag", lambda: "windows")
    monkeypatch.setattr(mime_mod.os, "add_dll_directory", lambda _path: (_ for _ in ()).throw(RuntimeError("dll")), raising=False)
    mime_mod._activate_dynamic_library_path(tmp_path)

    monkeypatch.setattr(mime_mod, "_candidate_library_names", lambda: ("missing.so", "broken.so", "libmagic.so"))
    broken = tmp_path / "broken.so"
    good = tmp_path / "libmagic.so"
    broken.write_text("broken", encoding="utf-8")
    good.write_text("good", encoding="utf-8")
    cdll_calls = []

    def _fake_cdll(path, mode=None):
        cdll_calls.append((Path(path).name, mode))
        if Path(path).name == "broken.so":
            raise RuntimeError("broken")
        return object()

    monkeypatch.setattr(ctypes, "CDLL", _fake_cdll)
    monkeypatch.delattr(ctypes, "RTLD_GLOBAL", raising=False)
    mime_mod._preload_libmagic_library(tmp_path)
    assert cdll_calls[-1][0] == "libmagic.so"


def test_conditions_helpers_build_expected_payloads():
    cond = conditions_mod.Condition({"path": "/flag"}, "==", True)
    assert cond.to_dict() == {"left": {"path": "/flag"}, "op": "==", "right": True}
    assert conditions_mod.Condition.AND(cond, {"x": 1}) == {
        "operator": "AND",
        "conditions": [cond.to_dict(), {"x": 1}],
    }
    assert conditions_mod.Condition.OR(cond, {"y": 2}) == {
        "operator": "OR",
        "conditions": [cond.to_dict(), {"y": 2}],
    }
    assert conditions_mod.Condition.bound("/current_path") == {
        "type": "store",
        "path": "/current_path",
        "scope": "auto",
        "default": None,
    }
