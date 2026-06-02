import inspect
from functools import wraps
from typing import Any, Dict, Optional, cast


def action(mod, name: Optional[str] = None):
    """Register an async UI action and inject standard SDK call arguments when needed."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )

        @wraps(func)
        async def wrapper(*args, **kwargs):
            if len(args) >= 3 and isinstance(args[0], dict):
                ctx, session, sdk = args[0], args[1], args[2]
                from democrai.core.application.handler.action_validation import (
                    get_action_validation,
                    validate_action_ctx,
                    validation_error_response,
                )

                validation = get_action_validation(func)
                if validation is not None:
                    validated_ctx, error_text = validate_action_ctx(reg_name, ctx, validation)
                    if error_text is not None:
                        return validation_error_response(sdk, error_text)
                    ctx = validated_ctx

                sig = inspect.signature(func)
                call_args = {}
                for param_name, param in sig.parameters.items():
                    if param_name == "ctx":
                        call_args[param_name] = ctx
                    elif param_name == "session":
                        call_args[param_name] = session
                    elif param_name in ["sdk", "module_sdk", "democrai_sdk"]:
                        call_args[param_name] = sdk
                    elif param_name in ctx:
                        call_args[param_name] = ctx[param_name]
                    elif param.default is not inspect.Parameter.empty:
                        call_args[param_name] = param.default

                from democrai.sdk.client import current_sdk

                token = current_sdk.set(sdk)
                try:
                    return await func(**call_args)
                finally:
                    current_sdk.reset(token)
            return await func(*args, **kwargs)

        if getattr(func, "_public_action", False):
            setattr(wrapper, "_public_action", True)
        if getattr(func, "_setup_only_action", False):
            setattr(wrapper, "_setup_only_action", True)
        validation = getattr(func, "_democrai_action_validation", None)
        if validation is not None:
            setattr(wrapper, "_democrai_action_validation", validation)

        mod.action_registry.register_action(reg_name, wrapper)
        return cast(type(func), wrapper)

    return decorator


def function(mod, name: Optional[str] = None):
    """Register a plain callable function in the SDK function registry."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )
        mod.action_registry.register_function(reg_name, func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return cast(type(func), wrapper)

    return decorator


def event_listener(mod, name: Optional[str] = None, priority: int = 0):
    """Register a fully qualified module event listener callback."""
    def decorator(func):
        reg_name = (name or "").strip()
        if not reg_name or "." not in reg_name:
            mod._event_warning(
                "Module event listener registration skipped: event keys must be fully qualified "
                f"(got '{name or func.__name__}')"
            )
            return func

        prefix = mod._get_module_prefix(func)
        mod.module_event_registry.register(
            reg_name, func, priority=priority, module_name=prefix or "core"
        )
        return func

    return decorator


def event_slot(
    mod,
    name: str,
    *,
    params: Optional[list[str]] = None,
    optional: bool = True,
    description: str = "",
):
    """Declare an event slot contract that listeners may implement."""
    def decorator(func):
        raw_name = (name or "").strip()
        prefix = mod._get_module_prefix(func)
        if not raw_name:
            mod._event_warning("Module event slot declaration skipped: empty event key")
            return func

        reg_name = (
            raw_name
            if (not prefix or raw_name.startswith(prefix + "."))
            else f"{prefix}.{raw_name}"
        )
        normalized_params = tuple(
            param for param in (params or []) if isinstance(param, str) and param
        )
        mod.module_event_registry.declare(
            reg_name,
            module_name=mod._get_registry_owner(prefix, reg_name),
            params=normalized_params,
            optional=optional,
            description=description,
        )
        return func

    return decorator
