from typing import Any, Dict, Optional, cast


def ui_template(mod, name: Optional[str] = None, priority: int = 0):
    """Register a UI template function in the shared template registry."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        reg_name = (
            name
            if name is not None
            else (f"{prefix}.{func.__name__}" if prefix else func.__name__)
        )
        mod.template_registry.register(reg_name, func, priority=priority)
        return func

    return decorator


def render_hook(mod, name: Optional[str] = None, priority: int = 0):
    """Register a fully qualified render hook handler for a module or core."""
    def decorator(func):
        reg_name = (name or "").strip()
        if not reg_name or "." not in reg_name:
            mod._hook_warning(
                "Render hook registration skipped: hook keys must be fully qualified "
                f"(got '{name or func.__name__}')"
            )
            return func

        prefix = mod._get_module_prefix(func)
        mod.render_hook_registry.register(
            reg_name, func, priority=priority, module_name=prefix or "core"
        )
        return func

    return decorator


def render_hook_slot(mod, name: str, *, optional: bool = True, description: str = ""):
    """Declare a render-hook slot that downstream modules can target."""
    def decorator(func):
        raw_name = (name or "").strip()
        prefix = mod._get_module_prefix(func)
        if not raw_name:
            mod._hook_warning("Render hook slot declaration skipped: empty hook key")
            return func

        reg_name = (
            raw_name
            if (not prefix or raw_name.startswith(prefix + "."))
            else f"{prefix}.{raw_name}"
        )
        mod.render_hook_registry.declare(
            reg_name,
            module_name=mod._get_registry_owner(prefix, reg_name),
            optional=optional,
            description=description,
        )
        return func

    return decorator
