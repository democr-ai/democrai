from __future__ import annotations

from typing import Any, Optional

from democrai.core.application.session_keys import SessionKey
from democrai.core.application.services.translation import get_translation_service
from democrai.core.platform.utils.identity import to_optional_int


class I18n:
    """Expose translation and language-resolution helpers to module code.

    The :class:`I18n` facade is the module-safe entrypoint for two common tasks:

    - resolving the effective language for the current user or an explicit user id
    - translating fully qualified keys loaded by the runtime translation registry

    The class keeps module code independent from the concrete translation service
    implementation.

    :param sdk: The current SDK instance that provides module metadata and session
        context.
    """

    def __init__(self, sdk) -> None:
        """Create an i18n facade bound to the current SDK request context.

        :param sdk: The active SDK instance for the current module request.
        """
        self.sdk = sdk

    def get_user_language(self, user_id: int | None = None) -> str:
        """Return the preferred language for a user.

        If ``user_id`` is omitted, the method falls back to the current session
        user. The returned value is always normalized to a string and defaults to
        ``"en"`` when the runtime cannot resolve a user-specific language.

        This method is useful when module code needs to choose content, locale
        files, or downstream integrations based on the user's preferred language
        without directly depending on the translation service internals.

        :param user_id: Optional explicit user identifier. When omitted, the
            method reads the current session user id from ``sdk.session``.
        :return: The resolved language code, for example ``"en"`` or ``"it"``.
        """
        resolved_user_id = to_optional_int(user_id)
        if resolved_user_id is None:
            session_user = (self.sdk.session or {}).get("user") or {}
            resolved_user_id = to_optional_int(session_user.get("id")) or 0
        service = get_translation_service()
        return service.get_user_language(resolved_user_id)

    def t(
        self,
        key: str,
        context: Optional[dict[str, Any]] = None,
        lang: Optional[str] = None,
    ) -> str:
        """Translate a key within the current module context.

        The method resolves the effective language using the following precedence:

        1. the explicit ``lang`` argument
        2. the language already stored in the current session
        3. the preferred language of the authenticated session user

        Translation keys must be fully qualified. The SDK does not prepend the
        current module name at runtime.

        :param key: Translation key to resolve, typically module-prefixed such as
            ``"system.user.list.title"``.
        :param context: Optional interpolation context passed to the translation
            service.
        :param lang: Optional explicit language override.
        :return: The translated string returned by the translation service.
        """
        user_lang = lang
        if not user_lang:
            session = self.sdk.session or {}
            session_lang = session.get(SessionKey.USER_LANGUAGE)
            if isinstance(session_lang, str) and session_lang.strip():
                user_lang = session_lang.strip().lower()

        if not user_lang:
            user = (self.sdk.session or {}).get("user", {})
            user_id = to_optional_int(user.get("id"))
            if user_id is not None:
                user_lang = get_translation_service().get_user_language(user_id)

        return get_translation_service().t(
            key,
            lang=user_lang,
            context=context,
        )
