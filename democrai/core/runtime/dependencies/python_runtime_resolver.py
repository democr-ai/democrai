from __future__ import annotations

import ast
import importlib.metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from democrai.core.runtime.dependencies.installer import install_python_packages
from democrai.core.runtime.dependencies.installer_env import runtime_env
from democrai.core.runtime.dependencies.engine_env import (
    get_engine_local_env_path,
    get_engine_local_tmp_path,
    has_engine_env_context,
)
from democrai.core.runtime.dependencies.extractor_env import (
    get_extractor_local_env_path,
    get_extractor_local_tmp_path,
    has_extractor_env_context,
)


_TORCH_CUDA_PROFILES: tuple[tuple[tuple[int, int], str], ...] = (
    ((13, 0), "cu130"),
    ((12, 8), "cu128"),
    ((12, 6), "cu126"),
    ((12, 4), "cu124"),
    ((12, 1), "cu121"),
    ((11, 8), "cu118"),
)

_TORCH_DISTRIBUTION_MODULES = {
    "torch": "torch",
    "torchaudio": "torchaudio",
    "torchvision": "torchvision",
}


@dataclass(frozen=True)
class TorchRuntimePlan:
    profile: str
    packages: tuple[str, ...]
    modules: tuple[str, ...]
    index_url: str


def _parse_version_pair(value: Any) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    parts = text.split(".", 2)
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        return None
    return major, minor


def resolve_torch_cuda_profile(env: dict[str, Any] | None = None) -> str:
    effective_env = dict(env or runtime_env())
    os_name = str(effective_env.get("os") or "").strip().lower()
    gpu = effective_env.get("gpu") if isinstance(effective_env.get("gpu"), dict) else {}
    if os_name not in {"linux", "windows"} or not bool(gpu.get("has_nvidia")):
        return "cpu"
    cuda_version = _parse_version_pair(gpu.get("cuda_driver_version"))
    if cuda_version is None:
        return "cpu"
    for minimum, profile in _TORCH_CUDA_PROFILES:
        if cuda_version >= minimum:
            return profile
    return "cpu"


def resolve_torch_runtime_plan(
    *,
    packages: list[str] | tuple[str, ...] | None = None,
    modules: list[str] | tuple[str, ...] | None = None,
    env: dict[str, Any] | None = None,
) -> TorchRuntimePlan:
    profile = resolve_torch_cuda_profile(env)
    resolved_packages = tuple(packages or ("torch",))
    resolved_modules = tuple(modules or ("torch",))
    return TorchRuntimePlan(
        profile=profile,
        packages=resolved_packages,
        modules=resolved_modules,
        index_url=f"https://download.pytorch.org/whl/{profile}",
    )


def install_torch_runtime(
    *,
    packages: list[str] | tuple[str, ...] | None = None,
    modules: list[str] | tuple[str, ...] | None = None,
    force: bool = False,
    env: dict[str, Any] | None = None,
    clean_target: bool = False,
) -> TorchRuntimePlan:
    plan = resolve_torch_runtime_plan(packages=packages, modules=modules, env=env)
    effective_force = force
    if not effective_force and not _installed_torch_matches_plan(plan):
        effective_force = True
    install_python_packages(
        list(plan.packages),
        modules=list(plan.modules),
        force=effective_force,
        index_url=plan.index_url,
        clean_target=clean_target,
    )
    return plan


def torch_runtime_matches_plan(
    *,
    packages: list[str] | tuple[str, ...] | None = None,
    modules: list[str] | tuple[str, ...] | None = None,
    env: dict[str, Any] | None = None,
) -> bool:
    plan = resolve_torch_runtime_plan(packages=packages, modules=modules, env=env)
    return _installed_torch_matches_plan(plan)


def _runtime_target_path() -> Path:
    if has_extractor_env_context():
        return get_extractor_local_env_path()
    if has_engine_env_context():
        return get_engine_local_env_path()
    raise RuntimeError("python_runtime_env_context_missing")


def _runtime_tmp_path() -> Path:
    if has_extractor_env_context():
        return get_extractor_local_tmp_path()
    if has_engine_env_context():
        return get_engine_local_tmp_path()
    raise RuntimeError("python_runtime_env_context_missing")


def _distribution_version_from_target(distribution_name: str, target: Path) -> str:
    versions = _distribution_versions_from_target(distribution_name, target)
    if len(versions) != 1:
        raise RuntimeError(
            f"distribution_version_ambiguous:{distribution_name}:{','.join(versions)}"
        )
    return versions[0]


def _distribution_versions_from_target(distribution_name: str, target: Path) -> list[str]:
    normalized_name = distribution_name.strip().lower().replace("_", "-")
    versions: list[str] = []
    for distribution in importlib.metadata.distributions(path=[str(target)]):
        metadata_name = str(distribution.metadata.get("Name") or "").strip().lower()
        if metadata_name.replace("_", "-") == normalized_name:
            version = str(distribution.version or "").strip()
            if version:
                versions.append(version)
    if versions:
        return sorted(set(versions))
    raise RuntimeError(f"distribution_not_found_in_python_runtime_env:{distribution_name}")


def _installed_torch_matches_plan(plan: TorchRuntimePlan) -> bool:
    target = _runtime_target_path()
    try:
        version = _installed_package_version("torch", target)
    except Exception:
        return False
    if not _installed_versions_match_requested_packages(plan.packages, target):
        return False
    normalized = version.lower()
    if plan.profile == "cpu":
        return "+cu" not in normalized
    return normalized.endswith(f"+{plan.profile}")


def _installed_versions_match_requested_packages(
    packages: tuple[str, ...], target: Path
) -> bool:
    for package_name, requested_version in _exact_requested_versions(packages).items():
        try:
            installed_version = _installed_package_version(package_name, target)
        except Exception:
            return False
        if installed_version.split("+", 1)[0] != requested_version.split("+", 1)[0]:
            return False
    return True


def _exact_requested_versions(packages: tuple[str, ...]) -> dict[str, str]:
    exact: dict[str, str] = {}
    for package in packages:
        name, separator, version = str(package or "").partition("==")
        if separator != "==":
            continue
        normalized_name = name.split("[", 1)[0].strip().lower().replace("_", "-")
        normalized_version = version.strip()
        if normalized_name and normalized_version:
            exact[normalized_name] = normalized_version
    return exact


def _installed_package_version(distribution_name: str, target: Path) -> str:
    module_version = _installed_module_version(distribution_name, target)
    if module_version:
        return module_version
    return _distribution_version_from_target(distribution_name, target)


def _installed_module_version(distribution_name: str, target: Path) -> str | None:
    module_name = _TORCH_DISTRIBUTION_MODULES.get(
        distribution_name.strip().lower().replace("_", "-")
    )
    if not module_name:
        return None
    version_file = target / module_name / "version.py"
    if not version_file.exists():
        return None
    try:
        tree = ast.parse(version_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target_node, ast.Name)
                and target_node.id == "__version__"
                for target_node in node.targets
            ) and isinstance(node.value, ast.Constant):
                return str(node.value.value or "").strip() or None
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__version__"
            and isinstance(node.value, ast.Constant)
        ):
            return str(node.value.value or "").strip() or None
    return None


def write_installed_torch_constraint(
    distributions: tuple[str, ...] = ("torch",),
) -> str:
    target = _runtime_target_path()
    path = _runtime_tmp_path() / "torch-constraints.txt"
    lines = [
        f"{distribution}=={_installed_package_version(distribution, target)}"
        for distribution in distributions
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(Path(path).resolve())
