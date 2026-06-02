from __future__ import annotations

from typing import List


def invalidate_module_routes(router, normalize_path, warmed_modules: set[str], module_name: str) -> None:
    if not module_name:
        return

    prefix = f"{module_name}/ui/"
    router._routes = [
        route for route in router._routes if not normalize_path(route.pattern).startswith(prefix)
    ]
    warmed_modules.discard(module_name)


def discover_module_patterns(module) -> List[str]:
    from democrai.core.platform.utils.discovery import discover_module_ui_modules

    full_modules = discover_module_ui_modules(module.name, module.path, module.is_builtin)
    module_prefix = f"modules.{module.name}.ui." if module.is_builtin else f"{module.name}.ui."

    patterns = []
    for module_name in full_modules:
        if not module_name.startswith(module_prefix):
            continue
        rel_module = module_name[len(module_prefix):]
        if rel_module:
            patterns.append(module.name + "/ui/" + rel_module.replace(".", "/"))
    return patterns


def ensure_module_routes(router, warmed_modules: set[str], module) -> None:
    if module.name in warmed_modules:
        return

    patterns = discover_module_patterns(module)
    if patterns:
        router.add_patterns(patterns)
    warmed_modules.add(module.name)
