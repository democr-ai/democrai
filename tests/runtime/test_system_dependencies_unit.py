from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import democrai.core.runtime.dependencies.system_dependencies as deps


def test_is_dependency_installed_paths(monkeypatch):
    monkeypatch.setattr(deps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(deps, "_is_ffmpeg_available", lambda: True)
    monkeypatch.setattr(deps, "_has_ffmpeg_dev_libraries", lambda: True)
    assert deps.is_dependency_installed("ffmpeg") is True

    monkeypatch.setattr(deps, "_is_ffmpeg_available", lambda: False)
    assert deps.is_dependency_installed("ffmpeg") is False

    monkeypatch.setattr(deps.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(deps, "_is_ffmpeg_available", lambda: True)
    assert deps.is_dependency_installed("ffmpeg") is True

    monkeypatch.setattr(deps, "_is_espeak_available", lambda: True)
    assert deps.is_dependency_installed("espeak") is True

    with pytest.raises(ValueError):
        deps.is_dependency_installed("bad-key")


def test_run_helpers_and_ffmpeg_checks(monkeypatch):
    calls = []
    monkeypatch.setattr(
        deps.subprocess,
        "run",
        lambda cmd, check=True, capture_output=True, text=True: calls.append(cmd),
    )
    assert deps._run(["echo", "ok"]) is True
    assert calls

    def _boom(*_a, **_k):
        raise RuntimeError("nope")

    monkeypatch.setattr(deps.subprocess, "run", _boom)
    assert deps._run(["x"]) is False

    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    assert deps._is_ffmpeg_available() is True

    monkeypatch.setattr(deps.shutil, "which", lambda _name: None)
    monkeypatch.setattr(deps, "_run", lambda cmd: cmd == ["ffmpeg", "-version"])
    assert deps._is_ffmpeg_available() is True

    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)
    assert deps._is_espeak_available() is True

    monkeypatch.setattr(deps.shutil, "which", lambda _name: None)
    monkeypatch.setattr(deps, "_run", lambda cmd: cmd == ["espeak", "--version"])
    assert deps._is_espeak_available() is True

    monkeypatch.setattr(deps.shutil, "which", lambda _name: None)
    assert deps._has_ffmpeg_dev_libraries() is False

    monkeypatch.setattr(deps.shutil, "which", lambda _name: "/usr/bin/pkg-config")
    monkeypatch.setattr(deps, "_run", lambda cmd: "--exists" in cmd)
    assert deps._has_ffmpeg_dev_libraries() is True


def test_linux_install_command_variants(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    assert deps._linux_install_command()[1] == "apt-get"

    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/dnf" if name == "dnf" else None)
    assert deps._linux_install_command()[1] == "dnf"

    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/pacman" if name == "pacman" else None)
    assert deps._linux_install_command()[1] == "pacman"

    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/zypper" if name == "zypper" else None)
    assert deps._linux_install_command()[1] == "zypper"

    monkeypatch.setattr(deps.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="No supported Linux package manager"):
        deps._linux_install_command()

    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    assert deps._linux_espeak_install_command()[-1] == "espeak-ng"


def test_install_preview_and_install_dependency_paths(monkeypatch):
    monkeypatch.setattr(deps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(deps, "_linux_install_command", lambda: ["sudo", "apt-get", "install"])
    assert deps.install_command_preview("ffmpeg") == "sudo apt-get install"

    monkeypatch.setattr(deps.platform, "system", lambda: "Darwin")
    assert deps.install_command_preview("ffmpeg") == "brew install ffmpeg pkg-config"
    assert deps.install_command_preview("espeak") == "brew install espeak-ng"

    monkeypatch.setattr(deps.platform, "system", lambda: "Windows")
    assert "winget install" in deps.install_command_preview("ffmpeg")
    assert "eSpeak-NG.eSpeak-NG" in deps.install_command_preview("espeak")

    monkeypatch.setattr(deps.platform, "system", lambda: "Plan9")
    assert "Unsupported OS" in deps.install_command_preview("ffmpeg")

    with pytest.raises(ValueError):
        deps.install_command_preview("bad")

    run_calls = []
    monkeypatch.setattr(deps.subprocess, "run", lambda cmd, check=True: run_calls.append(cmd))

    monkeypatch.setattr(deps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(deps, "_linux_install_command", lambda: ["sudo", "apt-get", "install"])
    deps.install_dependency("ffmpeg")
    assert run_calls[-1][0] == "sudo"

    monkeypatch.setattr(deps, "_linux_espeak_install_command", lambda: ["sudo", "apt-get", "install", "espeak-ng"])
    deps.install_dependency("espeak")
    assert run_calls[-1][-1] == "espeak-ng"

    monkeypatch.setattr(deps.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(deps.shutil, "which", lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    deps.install_dependency("ffmpeg")
    assert run_calls[-1][0] == "brew"
    deps.install_dependency("espeak")
    assert run_calls[-1] == ["brew", "install", "espeak-ng"]

    monkeypatch.setattr(deps.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="Homebrew is required"):
        deps.install_dependency("ffmpeg")

    monkeypatch.setattr(deps.platform, "system", lambda: "Windows")
    monkeypatch.setattr(deps.shutil, "which", lambda name: "C:/winget.exe" if name == "winget" else None)
    deps.install_dependency("ffmpeg")
    assert run_calls[-1][0] == "winget"
    deps.install_dependency("espeak")
    assert run_calls[-1] == ["winget", "install", "--id", "eSpeak-NG.eSpeak-NG", "-e"]

    monkeypatch.setattr(
        deps.shutil,
        "which",
        lambda name: "C:/choco.exe" if name == "choco" else None,
    )
    deps.install_dependency("ffmpeg")
    assert run_calls[-1][0] == "choco"

    monkeypatch.setattr(deps.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="winget or choco"):
        deps.install_dependency("ffmpeg")

    monkeypatch.setattr(deps.platform, "system", lambda: "Solaris")
    with pytest.raises(RuntimeError, match="Unsupported OS"):
        deps.install_dependency("ffmpeg")

    with pytest.raises(ValueError):
        deps.install_dependency("bad")


def test_install_script_invocation_and_fallback(monkeypatch, tmp_path):
    script = tmp_path / "install_system_dependency.py"
    script.write_text("print('ok')", encoding="utf-8")
    monkeypatch.setattr(deps, "_install_script_path", lambda: script)
    run_calls = []
    monkeypatch.setattr(
        deps.subprocess,
        "run",
        lambda cmd, check=True: run_calls.append(cmd),
    )
    monkeypatch.setattr(deps.sys, "executable", "/usr/bin/python3")
    deps.install_dependency_via_script("ffmpeg")
    assert run_calls and run_calls[-1][0] == "/usr/bin/python3"

    missing = tmp_path / "missing.py"
    install_calls = []
    monkeypatch.setattr(deps, "_install_script_path", lambda: missing)
    monkeypatch.setattr(deps, "install_dependency", lambda key: install_calls.append(key))
    deps.install_dependency_via_script("FFMPEG")
    assert install_calls == ["ffmpeg"]


def test_install_script_path_points_to_application_scripts():
    path = deps._install_script_path()
    assert isinstance(path, Path)
    assert path.name == "install_system_dependency.py"
    assert "scripts" in str(path)
