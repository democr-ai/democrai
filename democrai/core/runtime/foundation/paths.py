from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
try:
    import pwd
except Exception:  # pragma: no cover
    pwd = None

APP_NAME = "democrai"
MODULES_PATH_ENV = "DEMOCRAI_MODULES_PATH"
ENGINES_PATH_ENV = "DEMOCRAI_ENGINES_PATH"
EXTRACTORS_PATH_ENV = "DEMOCRAI_EXTRACTORS_PATH"
HOME_DIR_ENV = "DEMOCRAI_HOME_DIR"
_AF_UNIX_SOCKET_PATH_LIMIT = 100


def _strip_windows_extended_path(path: str) -> str:
    if not path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    return path[4:]


def logical_path(path: str | os.PathLike[str]) -> str:
    """Return a normal application path, never a Windows extended-length path."""

    value = os.fsdecode(os.fspath(path))
    if os.name != "nt":
        return value
    return _strip_windows_extended_path(value)


def windows_extended_path(path: str | os.PathLike[str]) -> str:
    """Return a Windows extended-length path for filesystem syscalls.

    Application state should keep normal paths. This helper is only for the
    boundary where Python hands a local path to Windows.
    """

    value = os.fsdecode(os.fspath(path))
    if os.name != "nt":
        return value
    if value.startswith("\\\\?\\"):
        return value
    absolute = os.path.abspath(os.path.expanduser(value))
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC" + absolute[1:]
    return "\\\\?\\" + absolute


def fs_path(path: str | os.PathLike[str]) -> str:
    return windows_extended_path(path)


def fs_parent_mkdir(path: str | os.PathLike[str]) -> None:
    parent = os.path.dirname(logical_path(path))
    if parent:
        os.makedirs(fs_path(parent), exist_ok=True)


@contextmanager
def fs_open(path: str | os.PathLike[str], *args, **kwargs) -> Iterator:
    handle = open(fs_path(path), *args, **kwargs)
    try:
        yield handle
    finally:
        handle.close()


def fs_exists(path: str | os.PathLike[str]) -> bool:
    return os.path.exists(fs_path(path))


def fs_is_file(path: str | os.PathLike[str]) -> bool:
    return os.path.isfile(fs_path(path))


def fs_is_dir(path: str | os.PathLike[str]) -> bool:
    return os.path.isdir(fs_path(path))


def fs_stat(path: str | os.PathLike[str]):
    return os.stat(fs_path(path))


def fs_unlink(path: str | os.PathLike[str], *, missing_ok: bool = False) -> None:
    try:
        os.unlink(fs_path(path))
    except FileNotFoundError:
        if not missing_ok:
            raise


def fs_rmtree(path: str | os.PathLike[str], **kwargs) -> None:
    shutil.rmtree(fs_path(path), **kwargs)


def fs_read_bytes(path: str | os.PathLike[str]) -> bytes:
    with fs_open(path, "rb") as handle:
        return handle.read()


def fs_write_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    fs_parent_mkdir(path)
    with fs_open(path, "wb") as handle:
        handle.write(data)


def fs_read_text(path: str | os.PathLike[str], *args, **kwargs) -> str:
    with fs_open(path, "r", *args, **kwargs) as handle:
        return handle.read()


def fs_write_text(path: str | os.PathLike[str], data: str, *args, **kwargs) -> None:
    fs_parent_mkdir(path)
    with fs_open(path, "w", *args, **kwargs) as handle:
        handle.write(data)


def _mkdir(path: Path) -> Path:
    try:
        os.makedirs(fs_path(path), exist_ok=True)
    except Exception:
        # Logger may not be initialized yet.
        logged = False
        app_ctx = getattr(sys, "app_ctx", None)
        if app_ctx is not None:
            logger = getattr(app_ctx(), "logger", None)
            if logger is not None:
                logger.error(f"Failed to create directory: {path}", exc_info=True)
                logged = True
        if not logged:
            print(f"MAKEDIR FAIL: {path}")
    return path


def is_frozen() -> bool:
    """Robust check for frozen/compiled runtime environments."""
    return (
        getattr(sys, "frozen", False)
        or "__compiled__" in globals()
        or hasattr(sys, "nuitka_binary_dir")
    )


def get_base_dir() -> str:
    """
    Base directory for the democrai package in dev and frozen modes.

    Dev:
      .../application/democrai/core/runtime/foundation/paths.py -> .../application/democrai
    Frozen standalone/onefile:
      directory containing the executable
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))

    # democrai/core/runtime/foundation/paths.py -> democrai package root
    return str(Path(__file__).resolve().parents[3])


def _home() -> Path:
    raw_democrai_home = str(os.environ.get(HOME_DIR_ENV) or "").strip()
    if raw_democrai_home and not raw_democrai_home.startswith("~"):
        return Path(raw_democrai_home)
    raw_elevated_uid = os.environ.get("SUDO_UID")
    if raw_elevated_uid is None:
        raw_elevated_uid = os.environ.get("PKEXEC_UID")
    elevated_uid = (
        raw_elevated_uid.strip() if isinstance(raw_elevated_uid, str) else ""
    )
    if elevated_uid and pwd is not None and sys.platform not in {"win32"}:
        try:
            return Path(pwd.getpwuid(int(elevated_uid)).pw_dir)
        except Exception:
            pass
    raw_home = str(os.environ.get("HOME") or "").strip()
    if raw_home and not raw_home.startswith("~"):
        return Path(raw_home)
    if pwd is not None and sys.platform not in {"win32"}:
        try:
            return Path(pwd.getpwuid(os.getuid()).pw_dir)
        except Exception:
            pass
    return Path.home()


def _xdg_path(env_name: str, fallback: Path) -> Path:
    raw_env = os.environ.get(env_name)
    raw = raw_env.strip() if isinstance(raw_env, str) else ""
    return Path(raw).expanduser() if raw else fallback


def _windows_appdata() -> Path:
    return Path(
        os.environ.get("APPDATA")
        or os.environ.get("LOCALAPPDATA")
        or (_home() / "AppData" / "Roaming")
    )


def _windows_localdata() -> Path:
    return Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or (_home() / "AppData" / "Local")
    )


def _data_root() -> Path:
    if sys.platform == "win32":
        return _windows_appdata() / APP_NAME
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / APP_NAME
    base = _xdg_path("XDG_DATA_HOME", _home() / ".local" / "share") / APP_NAME
    legacy_nested = base / APP_NAME

    # Preserve existing Linux/XDG installs created by the previous Qt-based path
    # strategy, which stored persistent data under ~/.local/share/democrai/democrai.
    if legacy_nested.exists():
        return legacy_nested
    return base


def _config_root() -> Path:
    if sys.platform == "win32":
        return _windows_appdata() / APP_NAME
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / APP_NAME / "config"
    return _xdg_path("XDG_CONFIG_HOME", _home() / ".config") / APP_NAME


def _cache_root() -> Path:
    if sys.platform == "win32":
        return _windows_localdata() / APP_NAME / "Cache"
    if sys.platform == "darwin":
        return _home() / "Library" / "Caches" / APP_NAME
    return _xdg_path("XDG_CACHE_HOME", _home() / ".cache") / APP_NAME


def _state_root() -> Path:
    if sys.platform == "win32":
        return _windows_localdata() / APP_NAME / "State"
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / APP_NAME / "state"
    return _xdg_path("XDG_STATE_HOME", _home() / ".local" / "state") / APP_NAME


def config_dir() -> Path:
    return _mkdir(_config_root())


def data_dir() -> Path:
    return _mkdir(_data_root())


def cache_dir() -> Path:
    return _mkdir(_cache_root())


def state_dir() -> Path:
    return _mkdir(_state_root())


def logs_dir() -> Path:
    return _mkdir(state_dir() / "logs")


def tmp_dir() -> Path:
    return _mkdir(data_dir() / "tmp")


def runtime_ipc_dir() -> Path:
    candidate = state_dir() / "ipc"
    if os.name == "nt" or len(str(candidate)) + 64 <= _AF_UNIX_SOCKET_PATH_LIMIT:
        return _mkdir(candidate)
    raw_uid = str(os.getuid()) if hasattr(os, "getuid") else "user"
    digest = hashlib.sha1(str(candidate).encode("utf-8")).hexdigest()[:12]
    path = _short_runtime_ipc_base() / f"dc-ipc-{raw_uid}-{digest}"
    _mkdir(path)
    try:
        path.chmod(0o700)
    except Exception:
        pass
    return path


def _short_runtime_ipc_base() -> Path:
    # Reserve room for "/dc-ipc-<uid>-<12 hex>" plus "/<16 hex>.sock".
    suffix_budget = 56
    candidates = [Path(tempfile.gettempdir())]
    if sys.platform != "win32":
        candidates.extend(Path(path) for path in ("/tmp", "/var/tmp"))
    for candidate in candidates:
        if len(str(candidate)) + suffix_budget <= _AF_UNIX_SOCKET_PATH_LIMIT:
            return candidate
    return Path("/tmp")


def runtime_unix_socket_path(filename: str) -> Path:
    name = Path(str(filename or "").strip()).name or "runtime.sock"
    directory = runtime_ipc_dir()
    candidate = directory / name
    if os.name == "nt" or len(str(candidate)) <= _AF_UNIX_SOCKET_PATH_LIMIT:
        return candidate
    suffix = Path(name).suffix or ".sock"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]
    shortened = directory / f"{digest}{suffix}"
    if len(str(shortened)) > _AF_UNIX_SOCKET_PATH_LIMIT:
        raise RuntimeError(
            f"Unix socket path exceeds the AF_UNIX limit "
            f"({_AF_UNIX_SOCKET_PATH_LIMIT} chars): {shortened}"
        )
    return shortened


def configure_temp_environment() -> str:
    path = str(tmp_dir())
    os.environ["TMPDIR"] = path
    os.environ["TEMP"] = path
    os.environ["TMP"] = path
    tempfile.tempdir = None
    return path


def get_data_dir() -> str:
    return str(data_dir())


def resolve_model_path(path: str) -> str:
    raw_path = path.strip() if isinstance(path, str) else ""
    if not raw_path:
        return raw_path

    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return raw_path


def _get_runtime_dirs(env_name: str) -> tuple[str, ...]:
    raw_paths = os.environ.get(env_name, "")
    seen: set[str] = set()
    resolved_paths: list[str] = []
    for candidate in raw_paths.split(os.pathsep):
        candidate = candidate.strip()
        if not candidate:
            continue
        expanded = os.path.expanduser(candidate)
        absolute = os.path.abspath(expanded)
        real = os.path.realpath(absolute)
        if real in seen or not os.path.isdir(real):
            continue
        seen.add(real)
        resolved_paths.append(real)
    return tuple(resolved_paths)


def get_runtime_module_dirs() -> tuple[str, ...]:
    return _get_runtime_dirs(MODULES_PATH_ENV)


def get_runtime_engine_dirs() -> tuple[str, ...]:
    return _get_runtime_dirs(ENGINES_PATH_ENV)


def get_runtime_extractor_dirs() -> tuple[str, ...]:
    return _get_runtime_dirs(EXTRACTORS_PATH_ENV)


def get_user_skills_dir() -> str:
    return str(_mkdir(data_dir() / "skills"))


def get_builtin_skills_dir() -> str:
    return os.path.join(get_base_dir(), "skills")
