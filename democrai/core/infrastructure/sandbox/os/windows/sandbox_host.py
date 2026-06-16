"""Per-child "sandbox-host" executable: the WFP identity carrier.

WFP keys egress filters on a process's app-id (its executable path). Sandboxed
children are launched from the same interpreter as the trusted parent, so to
give the confined children a *distinct* identity we launch them from a hardlink
of the interpreter placed **in the same directory** — same directory preserves
Python's venv/stdlib resolution (prefix is derived from the exe's folder), while
the distinct filename yields a distinct app-id WFP can match.

Creation needs write access to the interpreter's directory, which only a
medium-integrity process has (the first core relaunch). The Low-integrity core
that later spawns workers cannot create it, so the medium creator publishes the
path via ``DEMOCRAI_OS_SANDBOX_HOST_EXE`` and Low children reuse it.

``sys.executable`` inside a child launched from the host exe is the host exe, so
``allow_all`` children (which must NOT be confined) are mapped back to the real
interpreter via :func:`real_interpreter` to avoid inheriting the confined
identity.
"""

from __future__ import annotations

import os
import shutil
import threading

SANDBOX_HOST_ENV = "DEMOCRAI_OS_SANDBOX_HOST_EXE"
_HOST_STEM_SUFFIX = "-democrai-sandbox"

_cache: dict[str, str] = {}
_lock = threading.Lock()


def _host_path_for(interpreter: str) -> str:
    directory = os.path.dirname(interpreter)
    stem, ext = os.path.splitext(os.path.basename(interpreter))
    return os.path.join(directory, f"{stem}{_HOST_STEM_SUFFIX}{ext}")


def is_sandbox_host(path: str) -> bool:
    stem, _ext = os.path.splitext(os.path.basename(str(path or "")))
    return stem.endswith(_HOST_STEM_SUFFIX)


def real_interpreter(path: str) -> str:
    """Map a sandbox-host exe path back to the real interpreter path.

    Idempotent for non-host paths. Lets ``allow_all`` launches de-confine even
    when ``command[0]`` is ``sys.executable`` resolved to the host exe.
    """
    raw = str(path or "")
    if not is_sandbox_host(raw):
        return raw
    directory = os.path.dirname(raw)
    stem, ext = os.path.splitext(os.path.basename(raw))
    return os.path.join(directory, f"{stem[: -len(_HOST_STEM_SUFFIX)]}{ext}")


def existing_sandbox_host() -> str | None:
    raw = str(os.environ.get(SANDBOX_HOST_ENV, "") or "").strip()
    if raw and os.path.exists(raw):
        return raw
    return None


def ensure_sandbox_host_executable(interpreter: str) -> str:
    """Return a distinct-path interpreter for WFP identity, creating it if needed.

    Resolution order: the env-published host (Low workers reuse it) → cache →
    an existing on-disk host → create it in-place (hardlink, fallback copy).
    Raises ``RuntimeError`` if no host can be obtained — the caller fails closed
    rather than launching an unconfined child.
    """
    env_host = existing_sandbox_host()
    if env_host is not None:
        return env_host
    source = os.path.abspath(real_interpreter(interpreter))
    with _lock:
        cached = _cache.get(source)
        if cached and os.path.exists(cached):
            return cached
        host = _host_path_for(source)
        if os.path.exists(host):
            _cache[source] = host
            return host
        try:
            os.link(source, host)
        except OSError:
            try:
                shutil.copy2(source, host)
            except OSError as exc:
                raise RuntimeError(
                    f"windows_sandbox_host_executable_unavailable:{host}"
                ) from exc
        _cache[source] = host
        return host
