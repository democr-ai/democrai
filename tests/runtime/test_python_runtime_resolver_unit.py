from __future__ import annotations

from pathlib import Path

import democrai.core.runtime.dependencies.python_runtime_resolver as resolver_mod


def _env(os_name: str) -> dict:
    return {
        "os": os_name,
        "arch": "x86_64",
        "python": "3.12",
        "gpu": {"has_nvidia": False},
    }


def test_torch_runtime_plan_keeps_macos_torch_pins():
    plan = resolver_mod.resolve_torch_runtime_plan(
        packages=(
            "torch==2.10.0",
            "torchvision==0.25.0",
            "torchaudio==2.10.0",
            "soundfile",
        ),
        modules=("torch", "torchvision", "torchaudio"),
        env=_env("darwin"),
    )

    assert plan.profile == "cpu"
    assert plan.index_url is None
    assert plan.packages == (
        "torch==2.10.0",
        "torchvision==0.25.0",
        "torchaudio==2.10.0",
        "soundfile",
    )
    assert plan.modules == ("torch", "torchvision", "torchaudio")


def test_torch_runtime_plan_keeps_linux_torch_pins():
    packages = ("torch==2.10.0", "torchvision==0.25.0", "torchaudio==2.10.0")

    plan = resolver_mod.resolve_torch_runtime_plan(
        packages=packages,
        modules=("torch", "torchvision", "torchaudio"),
        env=_env("linux"),
    )

    assert plan.profile == "cpu"
    assert plan.packages == packages


def test_torch_runtime_plan_keeps_windows_torch_pins():
    packages = ("torch==2.10.0", "torchvision==0.25.0", "torchaudio==2.10.0")

    plan = resolver_mod.resolve_torch_runtime_plan(
        packages=packages,
        modules=("torch", "torchvision", "torchaudio"),
        env=_env("windows"),
    )

    assert plan.profile == "cpu"
    assert plan.packages == packages


def test_install_torch_runtime_uses_resolved_platform_packages(monkeypatch, tmp_path: Path):
    calls = {}

    monkeypatch.setattr(resolver_mod, "_runtime_target_path", lambda: tmp_path)
    monkeypatch.setattr(resolver_mod, "_installed_torch_matches_plan", lambda _plan: False)

    def _install_python_packages(packages, **kwargs):
        calls["packages"] = packages
        calls["kwargs"] = kwargs
        return True

    monkeypatch.setattr(resolver_mod, "install_python_packages", _install_python_packages)

    plan = resolver_mod.install_torch_runtime(
        packages=("torch==2.10.0", "torchaudio==2.10.0"),
        modules=("torch", "torchaudio"),
        env=_env("darwin"),
    )

    assert plan.packages == ("torch==2.10.0", "torchaudio==2.10.0")
    assert calls["packages"] == ["torch==2.10.0", "torchaudio==2.10.0"]
    assert calls["kwargs"]["modules"] == ["torch", "torchaudio"]
    assert calls["kwargs"]["index_url"] is None


def test_torch_runtime_plan_does_not_duplicate_numpy_constraint():
    plan = resolver_mod.resolve_torch_runtime_plan(
        packages=("torch==2.10.0", "numpy<2"),
        modules=("torch",),
        env=_env("darwin"),
    )

    assert plan.packages == ("torch==2.10.0", "numpy<2")


def test_torch_runtime_plan_keeps_macos_bare_torch_package():
    plan = resolver_mod.resolve_torch_runtime_plan(
        packages=("torch",),
        modules=("torch",),
        env=_env("darwin"),
    )

    assert plan.packages == ("torch",)
    assert plan.index_url is None


def test_torch_runtime_plan_keeps_non_exact_torch_range():
    plan = resolver_mod.resolve_torch_runtime_plan(
        packages=("torch>=2.4",),
        modules=("torch",),
        env=_env("darwin"),
    )

    assert plan.packages == ("torch>=2.4",)


def test_numpy_v1_constraint_depends_on_resolved_torch_version_not_os():
    mac_plan = resolver_mod.resolve_torch_runtime_plan(
        packages=("torch==2.4.0",),
        modules=("torch",),
        env=_env("darwin"),
    )
    linux_plan = resolver_mod.resolve_torch_runtime_plan(
        packages=("torch==2.2.2",),
        modules=("torch",),
        env=_env("linux"),
    )

    assert mac_plan.packages == ("torch==2.4.0",)
    assert linux_plan.packages == ("torch==2.2.2", "numpy<2")


def test_torch_runtime_match_rejects_numpy_two_for_numpy_v1_plan(monkeypatch, tmp_path: Path):
    plan = resolver_mod.resolve_torch_runtime_plan(
        packages=("torch==2.10.0",),
        modules=("torch",),
        env=_env("darwin"),
    )
    versions = {"torch": "2.10.0"}

    monkeypatch.setattr(resolver_mod, "_runtime_target_path", lambda: tmp_path)
    monkeypatch.setattr(
        resolver_mod,
        "_installed_package_version",
        lambda distribution_name, _target: versions[distribution_name],
    )

    assert resolver_mod._installed_torch_matches_plan(plan) is True

    old_plan = resolver_mod.resolve_torch_runtime_plan(
        packages=("torch==2.2.2",),
        modules=("torch",),
        env=_env("darwin"),
    )
    versions = {"torch": "2.2.2", "numpy": "2.3.5"}
    assert resolver_mod._installed_torch_matches_plan(old_plan) is False

    versions["numpy"] = "1.26.4"
    assert resolver_mod._installed_torch_matches_plan(old_plan) is True


def test_torch_runtime_match_rejects_installed_torch_below_minimum(monkeypatch, tmp_path: Path):
    plan = resolver_mod.resolve_torch_runtime_plan(
        packages=("torch>=2.6",),
        modules=("torch",),
        env=_env("darwin"),
    )
    versions = {"torch": "2.2.2"}

    monkeypatch.setattr(resolver_mod, "_runtime_target_path", lambda: tmp_path)
    monkeypatch.setattr(
        resolver_mod,
        "_installed_package_version",
        lambda distribution_name, _target: versions[distribution_name],
    )

    assert resolver_mod._installed_torch_matches_plan(plan) is False

    versions["torch"] = "2.6.0"
    assert resolver_mod._installed_torch_matches_plan(plan) is True


def test_write_installed_torch_constraint_adds_numpy_v1_for_old_torch(monkeypatch, tmp_path: Path):
    target = tmp_path / "target"
    runtime_tmp = tmp_path / "runtime-tmp"
    runtime_tmp.mkdir()

    monkeypatch.setattr(resolver_mod, "_runtime_target_path", lambda: target)
    monkeypatch.setattr(resolver_mod, "_runtime_tmp_path", lambda: runtime_tmp)
    monkeypatch.setattr(
        resolver_mod,
        "_installed_package_version",
        lambda distribution_name, _target: {
            "torch": "2.2.2",
            "torchaudio": "2.2.2",
        }[distribution_name],
    )

    constraint_path = resolver_mod.write_installed_torch_constraint(
        distributions=("torch", "torchaudio"),
    )

    assert (runtime_tmp / "torch-constraints.txt").read_text(encoding="utf-8") == (
        "torch==2.2.2\n"
        "torchaudio==2.2.2\n"
        "numpy<2\n"
        "fsspec<=2025.10.0,>=2023.1.0\n"
    )
    assert constraint_path == str((runtime_tmp / "torch-constraints.txt").resolve())
