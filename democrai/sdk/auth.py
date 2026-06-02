from typing import Any, Dict, Optional

from democrai.core.application.auth.action import permission_required, public, setup_only
from democrai.core.application.auth.jwt import (
    ALGORITMS_LENGTH,
    DEFAULT_ALGORITHM,
    create_access_token,
    decode_access_token,
)
from democrai.core.application.auth.roles import (
    ROLE_LEVEL_USER,
    is_super_role,
    normalize_role,
    resolve_primary_role,
)
from democrai.core.application.auth.service import (
    build_token_payload,
    get_user_permissions,
    login_user,
    refresh_session_token,
)
from democrai.core.application.session.service import SessionService
from democrai.core.application.session_keys import SessionKey
from democrai.core.platform.utils.identity import to_optional_int, to_required_int
from democrai.core.runtime.foundation.app import req_ctx


class AuthSDK:
    """Expose authentication helpers that modules are allowed to use.

    The authentication facade intentionally exposes a narrow surface. Module code
    can create access tokens in controlled contexts and refresh the current
    session token without importing low-level auth internals directly.

    The class also encapsulates the payload normalization rules used by the
    application runtime, such as role normalization, access-level propagation,
    and organization scoping.

    :param sdk_instance: The active SDK instance for the current request.
    """

    def __init__(self, sdk_instance):
        """Bind the auth facade to the current SDK instance.

        :param sdk_instance: The active SDK instance.
        """
        self.sdk = sdk_instance

    def create_token(
        self, data: Dict[str, Any], expires_delta: Optional[Any] = None
    ) -> str:
        """Create a JWT access token from an already prepared payload.

        This helper is the safe module-facing wrapper around the core JWT token
        generator. It should be used when module code needs a token for a trusted
        runtime flow and already knows the exact claims to embed.

        :param data: Claims payload to encode into the token.
        :param expires_delta: Optional expiration delta forwarded to the JWT
            generator.
        :return: The encoded JWT access token.
        """
        return create_access_token(data, expires_delta)

    @staticmethod
    def _build_token_payload(user_info: dict[str, Any]) -> dict[str, Any]:
        """Normalize user information into the token payload format.

        The method derives a single effective role, normalizes access scoping,
        and guarantees the presence of the standard claims expected by the rest
        of the runtime.

        :param user_info: User profile information returned by the auth layer.
        :return: A normalized token payload dictionary.
        """
        return build_token_payload(user_info)

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Run the core login flow for a username/password pair."""
        return login_user(username, password)

    def refresh_current_session_token(self) -> dict[str, Any]:
        """Refresh the JWT for the currently authenticated session user.

        The method is intentionally defensive. It verifies that:

        - a user is present in the current SDK session
        - the runtime request context identifies the same requester
        - the user still exists in the access profile store

        When the checks succeed, the method rebuilds the canonical token payload
        from the current user profile and returns a new token plus the payload
        that generated it.

        :return: A result dictionary with ``ok=True`` and token data on success,
            or ``ok=False`` plus structured error information on failure.
        """
        session = self.sdk.session or {}
        session_user = session.get("user") or {}
        session_user_id = to_optional_int(session_user.get("id"))

        current = None
        try:
            current = req_ctx()
        except Exception:
            current = None
        requester_id = current.user if current is not None else None
        return refresh_session_token(
            session_user_id=session_user_id,
            requester_id=requester_id,
        )
