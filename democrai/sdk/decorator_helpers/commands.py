from functools import wraps
from typing import Any, Dict, Optional, cast


def callable_command(mod, name: Optional[str] = None):
    """Register a command that can be invoked on demand through the command runtime."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        mod.action_registry.register_command(reg_name, wrapper)
        mod.module_command_registry.register(
            reg_name, wrapper, lifecycle="callable", module_name=prefix or "core"
        )
        return cast(type(func), wrapper)

    return decorator


def scheduled_command(
    mod,
    name: Optional[str] = None,
    *,
    cron: Optional[str] = None,
    interval_seconds: float | None = None,
):
    """Register a command scheduled by cron expression or fixed interval."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )
        mod.module_command_registry.register(
            reg_name,
            func,
            lifecycle="schedule",
            module_name=prefix or "core",
            cron=cron,
            interval_seconds=interval_seconds,
        )
        return func

    return decorator


def long_run_command(mod, name: Optional[str] = None, *, restart_on_exit: bool = True):
    """Register a long-lived command process managed by the module runtime."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )
        mod.module_command_registry.register(
            reg_name,
            func,
            lifecycle="long_run",
            module_name=prefix or "core",
            restart_on_exit=restart_on_exit,
        )
        return func

    return decorator


def single_run_command(mod, name: Optional[str] = None):
    """Register a boot-time command that is executed once during startup."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )
        mod.module_command_registry.register(
            reg_name, func, lifecycle="single_run", module_name=prefix or "core"
        )
        return func

    return decorator
