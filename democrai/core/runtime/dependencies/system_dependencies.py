from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from democrai.core.runtime.dependencies.env_constants import system_command_path


@dataclass(frozen=True)
class SystemDependencySpec:
    key: str
    display_name: str
    description: str


FFMPEG_PKG_CONFIG_LIBS = [
    "avformat",
    "avcodec",
    "avdevice",
    "avutil",
    "avfilter",
    "swscale",
    "swresample",
]


SYSTEM_DEPENDENCIES: dict[str, SystemDependencySpec] = {
    "espeak": SystemDependencySpec(
        key="espeak",
        display_name="eSpeak NG",
        description="Required by the local eSpeak text-to-speech engine.",
    ),
    "ffmpeg": SystemDependencySpec(
        key="ffmpeg",
        display_name="FFmpeg",
        description=(
            "Required by media/audio toolchains and Python packages that rely on libav."
        ),
    )
}


def _run(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)  # nosec B603
        return True
    except Exception:
        return False


def _sanitized_system_path() -> str:
    return system_command_path()


def _which_in_sanitized_path(command_name: str) -> str | None:
    resolved_command = command_name.strip()
    if not resolved_command:
        return None
    original_path = os.environ.get("PATH")
    os.environ["PATH"] = _sanitized_system_path()
    try:
        return shutil.which(resolved_command)
    finally:
        if original_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = original_path


def _is_ffmpeg_available() -> bool:
    if _which_in_sanitized_path("ffmpeg"):
        return True
    return _run(["ffmpeg", "-version"])


def _is_espeak_available() -> bool:
    os_name = platform.system().lower()
    candidates = {
        "linux": (
            "/usr/local/bin/espeak-ng",
            "/usr/local/bin/espeak",
            "/usr/bin/espeak-ng",
            "/usr/bin/espeak",
            "/bin/espeak-ng",
            "/bin/espeak",
        ),
        "darwin": (
            "/opt/homebrew/bin/espeak-ng",
            "/opt/homebrew/bin/espeak",
            "/opt/local/bin/espeak-ng",
            "/opt/local/bin/espeak",
            "/usr/local/bin/espeak-ng",
            "/usr/local/bin/espeak",
        ),
        "windows": (
            r"C:\Program Files\eSpeak NG\espeak-ng.exe",
            r"C:\Program Files\eSpeak NG\espeak.exe",
            r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe",
            r"C:\Program Files (x86)\eSpeak NG\espeak.exe",
        ),
    }.get(os_name, ())
    for raw_path in candidates:
        path = Path(raw_path)
        try:
            if path.exists() and path.is_file() and os.access(path, os.X_OK):
                return True
        except Exception:
            continue
    return False


def _has_ffmpeg_dev_libraries() -> bool:
    pkg_config = _which_in_sanitized_path("pkg-config")
    if not pkg_config:
        return False
    return _run([pkg_config, "--exists", *FFMPEG_PKG_CONFIG_LIBS])


def is_dependency_installed(key: str) -> bool:
    dep_key = key.strip().lower()
    if dep_key not in SYSTEM_DEPENDENCIES:
        raise ValueError(f"Unknown system dependency key: {key}")

    if dep_key == "espeak":
        return _is_espeak_available()

    os_name = platform.system().lower()
    if os_name == "linux":
        return _is_ffmpeg_available() and _has_ffmpeg_dev_libraries()
    return _is_ffmpeg_available()


def _linux_install_command() -> list[str]:
    if _which_in_sanitized_path("apt-get"):
        return [
            "sudo",
            "apt-get",
            "install",
            "-y",
            "pkg-config",
            "ffmpeg",
            "libavformat-dev",
            "libavcodec-dev",
            "libavdevice-dev",
            "libavutil-dev",
            "libavfilter-dev",
            "libswscale-dev",
            "libswresample-dev",
        ]
    if _which_in_sanitized_path("dnf"):
        return [
            "sudo",
            "dnf",
            "install",
            "-y",
            "pkgconf-pkg-config",
            "ffmpeg",
            "ffmpeg-devel",
        ]
    if _which_in_sanitized_path("pacman"):
        return ["sudo", "pacman", "-S", "--noconfirm", "pkgconf", "ffmpeg"]
    if _which_in_sanitized_path("zypper"):
        return ["sudo", "zypper", "--non-interactive", "install", "ffmpeg", "ffmpeg-devel", "pkgconf-pkg-config"]
    raise RuntimeError(
        "No supported Linux package manager found (apt-get/dnf/pacman/zypper)."
    )


def _linux_espeak_install_command() -> list[str]:
    if _which_in_sanitized_path("apt-get"):
        return ["sudo", "apt-get", "install", "-y", "espeak-ng"]
    if _which_in_sanitized_path("dnf"):
        return ["sudo", "dnf", "install", "-y", "espeak-ng"]
    if _which_in_sanitized_path("pacman"):
        return ["sudo", "pacman", "-S", "--noconfirm", "espeak-ng"]
    if _which_in_sanitized_path("zypper"):
        return ["sudo", "zypper", "--non-interactive", "install", "espeak-ng"]
    raise RuntimeError(
        "No supported Linux package manager found (apt-get/dnf/pacman/zypper)."
    )


def install_command_preview(key: str) -> str:
    dep_key = key.strip().lower()
    if dep_key not in SYSTEM_DEPENDENCIES:
        raise ValueError(f"Unknown system dependency key: {key}")

    os_name = platform.system().lower()
    if dep_key == "espeak":
        if os_name == "linux":
            return " ".join(_linux_espeak_install_command())
        if os_name == "darwin":
            return "brew install espeak-ng"
        if os_name == "windows":
            return "winget install --id eSpeak-NG.eSpeak-NG -e"
        return "Unsupported OS for automatic installation"

    if os_name == "linux":
        return " ".join(_linux_install_command())
    if os_name == "darwin":
        return "brew install ffmpeg pkg-config"
    if os_name == "windows":
        return "winget install --id Gyan.FFmpeg -e"
    return "Unsupported OS for automatic installation"


def install_dependency(key: str) -> None:
    dep_key = key.strip().lower()
    if dep_key not in SYSTEM_DEPENDENCIES:
        raise ValueError(f"Unknown system dependency key: {key}")

    os_name = platform.system().lower()
    if dep_key == "espeak":
        if os_name == "linux":
            cmd = _linux_espeak_install_command()
        elif os_name == "darwin":
            if not _which_in_sanitized_path("brew"):
                raise RuntimeError("Homebrew is required to install eSpeak NG on macOS.")
            cmd = ["brew", "install", "espeak-ng"]
        elif os_name == "windows":
            if _which_in_sanitized_path("winget"):
                cmd = ["winget", "install", "--id", "eSpeak-NG.eSpeak-NG", "-e"]
            elif _which_in_sanitized_path("choco"):
                cmd = ["choco", "install", "espeak-ng", "-y"]
            else:
                raise RuntimeError("winget or choco is required to install eSpeak NG on Windows.")
        else:
            raise RuntimeError(f"Unsupported OS for automatic installation: {os_name}")
    elif os_name == "linux":
        cmd = _linux_install_command()
    elif os_name == "darwin":
        if not _which_in_sanitized_path("brew"):
            raise RuntimeError("Homebrew is required to install FFmpeg on macOS.")
        cmd = ["brew", "install", "ffmpeg", "pkg-config"]
    elif os_name == "windows":
        if _which_in_sanitized_path("winget"):
            cmd = ["winget", "install", "--id", "Gyan.FFmpeg", "-e"]
        elif _which_in_sanitized_path("choco"):
            cmd = ["choco", "install", "ffmpeg", "-y"]
        else:
            raise RuntimeError("winget or choco is required to install FFmpeg on Windows.")
    else:
        raise RuntimeError(f"Unsupported OS for automatic installation: {os_name}")

    subprocess.run(cmd, check=True)  # nosec B603


def _install_script_path() -> Path:
    # application root from core/runtime/system_dependencies.py -> application/
    app_root = Path(__file__).resolve().parents[2]
    return app_root / "scripts" / "install_system_dependency.py"


def install_dependency_via_script(key: str) -> None:
    """Install a system dependency by invoking the dedicated installer script."""
    script_path = _install_script_path()
    dep_key = key.strip().lower()
    if not script_path.exists():
        # Fallback in case scripts are unavailable in the current runtime.
        install_dependency(dep_key)
        return
    subprocess.run([sys.executable, str(script_path), dep_key], check=True)  # nosec B603
