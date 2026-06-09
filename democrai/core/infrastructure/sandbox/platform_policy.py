from __future__ import annotations

import os
import sys


def platform_key() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform == "win32":
        return "win32"
    return sys.platform


LINUX_SYSTEM_PROBE_READ_PATHS = (
    "/etc/mime.types",
    "/etc/httpd/mime.types",
    "/etc/httpd/conf/mime.types",
    "/etc/apache/mime.types",
    "/etc/apache2/mime.types",
    "/var/www/etc/mime.types",
    "/usr/local/etc/httpd/conf/mime.types",
    "/usr/local/lib/netscape/mime.types",
    "/usr/local/etc/mime.types",
    "/etc/magic",
    "/usr/share/magic",
    "/usr/share/file/magic",
    "/usr/lib/magic",
    "/etc/ssl/certs",
    "/etc/ssl/openssl.cnf",
    "/etc/localtime",
    "/etc/hostname",
    "/etc/os-release",
    "/etc/xdg",
    "/etc/pip.conf",
    "/etc/zoneinfo",
    "/run",
    "/proc",
    "/sys",
    "/dev",
)

LINUX_RUNTIME_DEPENDENCY_READ_PATHS = (
    "/usr",
    "/usr/local",
    "/bin",
    "/sbin",
    "/lib",
    "/lib32",
    "/lib64",
    "~/.pip",
    "~/.config/pip",
    "~/.bun",
    "~/.cargo/bin",
    "~/.local/bin/rustc",
)

DARWIN_SYSTEM_PROBE_READ_PATHS = (
    "/private/etc",
    "/private/var",
    "/etc/zoneinfo",
    "/usr/lib/zoneinfo",
    "/usr/share/lib/zoneinfo",
    "/usr/share/zoneinfo",
    "/usr/share/zoneinfo.default",
    "/var/db/timezone",
    "/var/db/timezone/zoneinfo",
)

DARWIN_RUNTIME_DEPENDENCY_READ_PATHS = (
    "/System/Library",
    "/Library",
    "/usr/lib",
    "/usr/bin",
    "/usr/X11R6/lib/X11/fonts",
    "/usr/X11/lib/X11/fonts",
    "/usr/share/fonts",
    "/opt/homebrew",
    "/opt/local",
    "/usr/local",
    "/usr/local/share/fonts",
    "/Network/Library/Fonts",
    "~/.local/share/fonts",
    "~/.fonts",
)

WINDOWS_SYSTEM_PROBE_READ_FALLBACKS = (
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\ProgramData",
)

WINDOWS_RUNTIME_DEPENDENCY_READ_FALLBACKS = (
    r"C:\Program Files",
    r"C:\Program Files (x86)",
)

DARWIN_TOOLCHAIN_EXECUTE_PATHS = (
    "/usr/bin/cc",
    "/usr/bin/clang",
    "/usr/bin/as",
    "/usr/bin/ld",
    "/opt/homebrew/bin/clang",
    "/opt/homebrew/bin/as",
    "/opt/homebrew/bin/ld",
    "/opt/local/bin/clang",
    "/opt/local/bin/as",
    "/opt/local/bin/ld",
)

LINUX_TOOLCHAIN_EXECUTE_PATHS = (
    "/usr/bin/cc",
    "/usr/bin/gcc",
    "/usr/local/bin/gcc",
    "/usr/bin/clang",
    "/usr/local/bin/clang",
    "/usr/bin/as",
    "/usr/bin/x86_64-linux-gnu-as",
    "/usr/bin/ld",
    "/usr/bin/x86_64-linux-gnu-ld",
)


def _env_paths(*names: str) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        raw = os.environ.get(name)
        value = str(raw or "").strip()
        if value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def _windows_system_probe_read_paths() -> tuple[str, ...]:
    roots = list(_env_paths("SystemRoot", "WINDIR"))
    paths: list[str] = []
    for root in roots:
        paths.append(os.path.join(root, "System32"))
        paths.append(os.path.join(root, "SysWOW64"))
    paths.extend(_env_paths("ProgramData"))
    paths.extend(WINDOWS_SYSTEM_PROBE_READ_FALLBACKS)
    return tuple(dict.fromkeys(paths))


def _windows_runtime_dependency_read_paths() -> tuple[str, ...]:
    paths = [
        *_env_paths("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"),
        *WINDOWS_RUNTIME_DEPENDENCY_READ_FALLBACKS,
    ]
    return tuple(dict.fromkeys(paths))


def system_probe_read_paths(os_name: str | None = None) -> tuple[str, ...]:
    key = os_name or platform_key()
    if key == "linux":
        return LINUX_SYSTEM_PROBE_READ_PATHS
    if key == "darwin":
        return DARWIN_SYSTEM_PROBE_READ_PATHS
    if key == "win32":
        return _windows_system_probe_read_paths()
    return ()


def runtime_dependency_read_paths(os_name: str | None = None) -> tuple[str, ...]:
    key = os_name or platform_key()
    if key == "linux":
        return LINUX_RUNTIME_DEPENDENCY_READ_PATHS
    if key == "darwin":
        return DARWIN_RUNTIME_DEPENDENCY_READ_PATHS
    if key == "win32":
        return _windows_runtime_dependency_read_paths()
    return ()


def trusted_read_path_variants(paths: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    variants: list[str] = []
    for item in paths:
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            cheap = _cheap_trusted_read_path(raw)
        except Exception:
            continue
        variants.append(cheap)
        if not os.path.exists(cheap):
            continue
        try:
            real = os.path.realpath(cheap)
        except Exception:
            continue
        if real and real != cheap:
            variants.append(real)
    return tuple(dict.fromkeys(variants))


def _cheap_trusted_read_path(path: str) -> str:
    expanded = os.path.expanduser(str(path or "").strip())
    if _windows_path_like(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.abspath(expanded))


def _windows_path_like(path: str) -> bool:
    value = str(path or "").strip()
    return len(value) >= 2 and value[1] == ":" or value.startswith("\\\\")


def toolchain_execute_paths(os_name: str | None = None) -> tuple[str, ...]:
    key = os_name or platform_key()
    if key == "linux":
        return LINUX_TOOLCHAIN_EXECUTE_PATHS
    if key == "darwin":
        return DARWIN_TOOLCHAIN_EXECUTE_PATHS
    if key == "win32":
        return ()
    return ()


def platform_system_read_paths(os_name: str | None = None) -> tuple[str, ...]:
    return trusted_read_path_variants(
        tuple(
            dict.fromkeys(
                (
                    *system_probe_read_paths(os_name),
                    *runtime_dependency_read_paths(os_name),
                )
            )
        )
    )
