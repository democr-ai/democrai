from __future__ import annotations

import ctypes
import mimetypes
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from democrai.core.runtime.foundation.paths import get_base_dir

_MAGIC_LOCK = threading.Lock()
_MAGIC_INSTANCE = None
_MAGIC_UNAVAILABLE = False

_DEFAULT_MIME = "application/octet-stream"
_COMMON_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "application/json": ".json",
    "text/markdown": ".md",
}


@dataclass(frozen=True)
class MimeDetectionResult:
    mime_type: str
    source: str


def detect_mime_type(
    *,
    data: bytes | bytearray | memoryview | None,
    filename: str | None = None,
    declared_content_type: str | None = None,
) -> MimeDetectionResult:
    payload = bytes(data) if data is not None else b""
    declared = _normalize_content_type(declared_content_type)

    magic_mime = _detect_with_libmagic(payload)
    if magic_mime:
        return MimeDetectionResult(mime_type=magic_mime, source="libmagic")

    filetype_mime = _detect_with_filetype(payload)
    if filetype_mime:
        return MimeDetectionResult(mime_type=filetype_mime, source="filetype")

    if _looks_like_svg(payload):
        return MimeDetectionResult(mime_type="image/svg+xml", source="svg_sniff")

    guessed = _guess_from_filename(filename)
    if guessed:
        return MimeDetectionResult(mime_type=guessed, source="filename")

    if declared:
        return MimeDetectionResult(mime_type=declared, source="declared")

    return MimeDetectionResult(mime_type=_DEFAULT_MIME, source="default")


def extension_for_mime_type(content_type: str | None) -> str:
    normalized = _normalize_content_type(content_type)
    if not normalized:
        return ""
    if normalized in _COMMON_EXTENSIONS:
        return _COMMON_EXTENSIONS[normalized]
    guessed = mimetypes.guess_extension(normalized)
    return guessed if isinstance(guessed, str) else ""


def filename_hint_from_url(url: str | None) -> str:
    normalized = url.strip() if isinstance(url, str) else ""
    parsed = urlparse(normalized)
    return Path(parsed.path).name


def _normalize_content_type(content_type: str | None) -> str:
    raw = content_type.strip().lower() if isinstance(content_type, str) else ""
    if not raw:
        return ""
    return raw.split(";", 1)[0].strip()


def _guess_from_filename(filename: str | None) -> str:
    name = filename.strip() if isinstance(filename, str) else ""
    if not name:
        return ""
    guessed = mimetypes.guess_type(name)[0]
    return _normalize_content_type(guessed)


def _looks_like_svg(payload: bytes) -> bool:
    if not payload:
        return False
    head = payload[:4096].lstrip()
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:].lstrip()
    if head.startswith(b"<?xml"):
        return b"<svg" in head
    return head.startswith(b"<svg")


def _detect_with_filetype(payload: bytes) -> str:
    if not payload:
        return ""
    try:
        import filetype
    except Exception:
        return ""
    try:
        kind = filetype.guess(payload)
    except Exception:
        return ""
    if kind is None:
        return ""
    return _normalize_content_type(getattr(kind, "mime", ""))


def _detect_with_libmagic(payload: bytes) -> str:
    detector = _get_magic_instance()
    if detector is None or not payload:
        return ""
    try:
        return _normalize_content_type(detector.from_buffer(payload))
    except Exception:
        return ""


def _get_magic_instance():
    global _MAGIC_INSTANCE, _MAGIC_UNAVAILABLE
    if _MAGIC_UNAVAILABLE:
        return None
    if _MAGIC_INSTANCE is not None:
        return _MAGIC_INSTANCE

    with _MAGIC_LOCK:
        if _MAGIC_UNAVAILABLE:
            return None
        if _MAGIC_INSTANCE is not None:
            return _MAGIC_INSTANCE

        try:
            import magic as magic_mod  # type: ignore
        except Exception:
            _MAGIC_UNAVAILABLE = True
            return None

        magic_file = _prepare_libmagic_runtime()
        try:
            if magic_file:
                _MAGIC_INSTANCE = magic_mod.Magic(mime=True, magic_file=magic_file)
            else:
                _MAGIC_INSTANCE = magic_mod.Magic(mime=True)
        except Exception:
            _MAGIC_UNAVAILABLE = True
            _MAGIC_INSTANCE = None
            return None

        return _MAGIC_INSTANCE


def _prepare_libmagic_runtime() -> str | None:
    bundled_dir = _bundled_libmagic_dir()
    if bundled_dir is not None:
        _activate_dynamic_library_path(bundled_dir)
        _preload_libmagic_library(bundled_dir)
        magic_file = bundled_dir / "magic.mgc"
        if magic_file.exists():
            return str(magic_file)

    raw_env_magic = os.getenv("MAGIC")
    env_magic = raw_env_magic.strip() if isinstance(raw_env_magic, str) else ""
    if env_magic:
        return env_magic
    return None


def _bundled_libmagic_dir() -> Path | None:
    base = Path(get_base_dir())
    tag = _platform_tag()
    candidate = base / "third_party" / "libmagic" / tag
    if candidate.exists() and candidate.is_dir():
        return candidate
    return None


def _platform_tag() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _candidate_library_names() -> tuple[str, ...]:
    tag = _platform_tag()
    if tag == "windows":
        return ("magic1.dll", "libmagic-1.dll", "libmagic.dll")
    if tag == "macos":
        return ("libmagic.dylib", "libmagic.1.dylib")
    return ("libmagic.so.1", "libmagic.so")


def _activate_dynamic_library_path(lib_dir: Path) -> None:
    if _platform_tag() != "windows":
        return
    try:
        os.add_dll_directory(str(lib_dir))
    except Exception:
        pass


def _preload_libmagic_library(lib_dir: Path) -> None:
    for name in _candidate_library_names():
        candidate = lib_dir / name
        if not candidate.exists():
            continue
        try:
            if hasattr(ctypes, "RTLD_GLOBAL"):
                ctypes.CDLL(str(candidate), mode=ctypes.RTLD_GLOBAL)
            else:
                ctypes.CDLL(str(candidate))
            return
        except Exception:
            continue
