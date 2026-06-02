"""
Centralised constants for session dictionary keys.

All code that reads or writes the session dict should import from here
instead of using hardcoded strings, to make the full key surface
discoverable and refactoring-safe.
"""


class SessionKey:
    # Identity
    USER = "user"
    USER_LANGUAGE = "user_language"

    # Navigation
    CURRENT_PATH = "current_path"

    # UI state
    PENDING_MODAL = "pending_modal"
    ACTIVE_MAIN_TEMPLATE = "active_main_template"
    # Legacy variant written by older code; checked alongside ACTIVE_MAIN_TEMPLATE.
    ACTIVE_MAIN_TEMPLATE_LEGACY = "_active_main_template"

    # Permission cache (internal, engine-private)
    PERM_CACHE_USER = "_perm_cache_user"
    PERM_CACHE_TS = "_perm_cache_ts"
    PERM_CACHE_VALUES = "_perm_cache_values"

    # Auth / login flow
    POST_LOGIN_PATH = "post_login_path"
