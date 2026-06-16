import functools
from typing import List, Callable
from democrai.core.runtime.foundation.app import app_ctx


def permission_required(permissions: List[str]):
    """
    Decorator to mark an action function as requiring specific permissions.
    Usage: @permission_required(["view_admin", "edit_settings"])
    """

    def decorator(func: Callable):
        setattr(func, "_required_permissions", permissions)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # The actual enforcement will happen in the Core.handle
            # but we can optionally check here too if we have access to context.
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def public(func: Callable):
    setattr(func, "_public_action", True)
    return func


def allow_public_upload(func: Callable):
    setattr(func, "_allow_public_upload", True)
    return func


def setup_only(func: Callable):
    setattr(func, "_setup_only_action", True)
    return func


def _unwrap(func: Callable) -> Callable:
    actual_func = getattr(func, "__func__", func)
    while hasattr(actual_func, "__wrapped__"):
        actual_func = getattr(actual_func, "__wrapped__")
    return actual_func


def get_required_permissions(func: Callable) -> List[str]:
    """Helper to retrieve required permissions from a function."""
    return getattr(_unwrap(func), "_required_permissions", [])


def is_public_action(func: Callable) -> bool:
    return bool(getattr(_unwrap(func), "_public_action", False))


def allows_public_upload(func: Callable) -> bool:
    return bool(getattr(_unwrap(func), "_allow_public_upload", False))


def is_setup_only_action(func: Callable) -> bool:
    return bool(getattr(_unwrap(func), "_setup_only_action", False))


def check_access(required_permissions: List[str], user_permissions: List[str]) -> bool:
    """
    Checks if the user has access based on the 'at least one' rule.
    Returns True if no permissions are required or if the user possesses at least one.
    """
    if not required_permissions:
        logger = getattr(app_ctx(), "logger", None)
        if logger:
            # logger.warning(
            #    "check_access called with empty required_permissions, granting access by default."
            # )
            pass
        return True

    # Check if user has at least one of the required permissions
    for p in required_permissions:
        if p in user_permissions:
            return True

    return False
