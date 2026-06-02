from democrai.sdk.decorators import guest_page, home_page
from democrai.core.runtime.foundation.registry import guest_page_registry, home_page_registry

DEFAULT_HOME_PAGE = "/auth/profile"
DEFAULT_GUEST_PAGE = "/auth/login"
POST_LOGIN_PATH_KEY = "post_login_path"


@home_page(DEFAULT_HOME_PAGE, priority=0)
def _default_auth_profile_home():
    """Registers the built-in authenticated home page."""


@guest_page(DEFAULT_GUEST_PAGE, priority=0)
def _default_guest_page():
    """Registers the built-in unauthenticated entry page."""


def resolve_home_page_path() -> str:
    registration = home_page_registry.get_registration()
    if registration is not None:
        return registration.path
    return DEFAULT_HOME_PAGE


def resolve_guest_page_path() -> str:
    """
    Returns the path to the configured guest entry page (e.g., login).

    :return: The guest page path string.
    """
    registration = guest_page_registry.get_registration()
    if registration is not None:
        return registration.path
    return DEFAULT_GUEST_PAGE


def remember_post_login_path(session: dict, path: str | None) -> None:
    """
    Stores a path in the session to be redirected to after a successful login.

    :param session: The user session.
    :param path: The path to remember.
    """
    if not path or path == "/system/setup":
        return
    guest_path = resolve_guest_page_path()
    if path in {guest_path, DEFAULT_GUEST_PAGE}:
        return
    session[POST_LOGIN_PATH_KEY] = path


def clear_post_login_path(session: dict) -> None:
    session.pop(POST_LOGIN_PATH_KEY, None)


def consume_post_login_path(session: dict) -> str | None:
    path = session.pop(POST_LOGIN_PATH_KEY, None)
    if not isinstance(path, str) or not path:
        return None
    return path


def resolve_post_login_redirect_path(session: dict) -> str:
    """
    Determines where to redirect a user after login, prioritizing any 'remembered' path.

    :param session: The user session.
    :return: The redirect path string.
    """
    return consume_post_login_path(session) or resolve_home_page_path()
