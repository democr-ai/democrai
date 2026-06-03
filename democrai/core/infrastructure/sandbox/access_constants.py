from __future__ import annotations

import sys


LINUX_SYSTEM_READ_PATHS = (
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
    "/usr",
    "/etc/xdg",
    "/etc/pip.conf",
    "~/.pip",
    "~/.config/pip",
    "~/.bun",
    "~/.local/bin/rustc",
    "/bin",
    "/sbin",
    "~/.cargo/bin",
    "/usr/local",
    "/lib",
    "/lib32",
    "/lib64",
    "/run",
    "/proc",
    "/sys",
    "/dev",
    "/etc/zoneinfo",
)

DARWIN_SYSTEM_READ_PATHS = (
    "/private/etc",
    "/private/var",
    "/etc/zoneinfo",
    "/usr/lib/zoneinfo",
    "/usr/share/lib/zoneinfo",
    "/usr/share/zoneinfo",
    "/usr/share/zoneinfo.default",
    "/var/db/timezone/zoneinfo",
    "/opt/homebrew",
    "/opt/local",
)

WINDOWS_SYSTEM_READ_PATHS = (
    "C:\\Windows\\System32",
    "C:\\Windows\\SysWOW64",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
)


def system_read_paths() -> tuple[str, ...]:
    if sys.platform.startswith("linux"):
        return LINUX_SYSTEM_READ_PATHS
    if sys.platform == "darwin":
        return DARWIN_SYSTEM_READ_PATHS
    if sys.platform == "win32":
        return WINDOWS_SYSTEM_READ_PATHS
    return ()
