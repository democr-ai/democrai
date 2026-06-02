from __future__ import annotations

from typing import Optional


class Pages:
    """Expose application page-resolution helpers to modules.

    The page facade lets modules query the canonical navigation entrypoints that
    the core runtime currently exposes, such as the authenticated home page, the
    guest landing page, and the post-login redirect target.

    :param sdk: The active SDK instance for the current request.
    """

    def __init__(self, sdk) -> None:
        """Create a page helper bound to the current SDK instance.

        :param sdk: The active SDK instance.
        """
        self.sdk = sdk

    def get_home_path(self) -> str:
        """Return the canonical authenticated home-page path.

        Modules use this helper when they need to redirect users to the current
        home page without hardcoding a route.

        :return: The authenticated home-page path.
        """
        from democrai.core.application.home import resolve_home_page_path

        return resolve_home_page_path()

    def get_guest_path(self) -> str:
        """Return the canonical guest landing page path.

        :return: The guest entry path exposed by the application.
        """
        from democrai.core.application.home import resolve_guest_page_path

        return resolve_guest_page_path()

    def get_post_login_redirect_path(self, session: Optional[dict] = None) -> str:
        """Resolve the path that should be opened after login.

        The resolution can use an explicit ``session`` override or the current
        SDK session. This is useful when a module wants to compute navigation
        after a login or token-refresh flow using the same core rules as the
        main application.

        :param session: Optional explicit session payload to evaluate.
        :return: The resolved post-login redirect path.
        """
        from democrai.core.application.home import resolve_post_login_redirect_path

        return resolve_post_login_redirect_path(
            session if session is not None else self.sdk.session
        )
