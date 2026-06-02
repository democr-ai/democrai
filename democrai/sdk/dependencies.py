from __future__ import annotations

from typing import List, Optional

from democrai.core.runtime.dependencies.ai_bootstrap import ensure_import


__all__ = [
    "Dependencies",
    "ensure_import",
    "install_dependency",
    "install_dependencies",
    "install_python_packages",
    "install_torch_runtime",
    "resolve_torch_cuda_profile",
    "resolve_torch_runtime_plan",
    "torch_runtime_matches_plan",
    "write_installed_torch_constraint",
    "install_command_preview",
]


def install_dependencies(packages: List[str], force: bool = False) -> bool:
    from democrai.core.runtime.dependencies.installer import install_dependencies

    return install_dependencies(packages, force=force)


def install_dependency(package: str, force: bool = False) -> bool:
    from democrai.core.runtime.dependencies.installer import install_dependency

    return install_dependency(package, force=force)


def install_python_packages(
    packages: List[str],
    *,
    modules: List[str] | None = None,
    force: bool = False,
    index_url: str | None = None,
    extra_index_url: str | None = None,
    allow_source: bool = False,
    extra_pip_args: List[str] | None = None,
    env: dict[str, str] | None = None,
    clean_target: bool = False,
) -> bool:
    from democrai.core.runtime.dependencies.installer import install_python_packages

    return install_python_packages(
        packages,
        modules=modules,
        force=force,
        index_url=index_url,
        extra_index_url=extra_index_url,
        allow_source=allow_source,
        extra_pip_args=extra_pip_args,
        env=env,
        clean_target=clean_target,
    )


def install_torch_runtime(
    *,
    packages: list[str] | tuple[str, ...] | None = None,
    modules: list[str] | tuple[str, ...] | None = None,
    force: bool = False,
    env: dict | None = None,
    clean_target: bool = False,
):
    from democrai.core.runtime.dependencies.python_runtime_resolver import install_torch_runtime

    return install_torch_runtime(
        packages=packages,
        modules=modules,
        force=force,
        env=env,
        clean_target=clean_target,
    )


def resolve_torch_cuda_profile(env: dict | None = None) -> str:
    from democrai.core.runtime.dependencies.python_runtime_resolver import resolve_torch_cuda_profile

    return resolve_torch_cuda_profile(env=env)


def resolve_torch_runtime_plan(
    *,
    packages: list[str] | tuple[str, ...] | None = None,
    modules: list[str] | tuple[str, ...] | None = None,
    env: dict | None = None,
):
    from democrai.core.runtime.dependencies.python_runtime_resolver import resolve_torch_runtime_plan

    return resolve_torch_runtime_plan(packages=packages, modules=modules, env=env)


def torch_runtime_matches_plan(
    *,
    packages: list[str] | tuple[str, ...] | None = None,
    modules: list[str] | tuple[str, ...] | None = None,
    env: dict | None = None,
) -> bool:
    from democrai.core.runtime.dependencies.python_runtime_resolver import torch_runtime_matches_plan

    return torch_runtime_matches_plan(packages=packages, modules=modules, env=env)


def write_installed_torch_constraint(
    distributions: tuple[str, ...] = ("torch",),
) -> str:
    from democrai.core.runtime.dependencies.python_runtime_resolver import write_installed_torch_constraint

    return write_installed_torch_constraint(distributions=distributions)


def install_command_preview(key: str) -> str:
    from democrai.core.runtime.dependencies.system_dependencies import install_command_preview

    return install_command_preview(key)


class Dependencies:
    """Expose controlled dependency bootstrap helpers to module code."""

    def ensure_import(
        self,
        module_name: str,
        *,
        dependency_key: Optional[str] = None,
    ):
        """Ensure that a runtime dependency can be imported for the module.

        This helper delegates to the central dependency bootstrap logic. It is
        the supported way for modules to request a missing optional dependency
        without wiring their own import/install flow.

        :param module_name: Importable module name to validate or bootstrap.
        :param dependency_key: Optional logical dependency identifier when the
            runtime should map the request to a named dependency contract rather
            than the raw import name alone.
        :return: The result returned by the dependency bootstrap layer.
        """
        return ensure_import(module_name, dependency_key=dependency_key)
