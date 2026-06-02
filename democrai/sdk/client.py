from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import app_ctx


class SDK:
    """
    Main SDK entrypoint with domain-based surface.
    """

    def __init__(
        self,
        module_path: str,
        module_name: str,
        current_path: str = "",
        session: Optional[dict] = None,
    ):
        """Create the SDK bound to one module and request/session context."""
        self.module_path = module_path
        self.module_name = module_name
        self.current_path = current_path
        self.session = session if session is not None else {}

        from democrai.sdk.access import Access
        from democrai.sdk.ai import AI
        from democrai.sdk.auth import AuthSDK
        from democrai.sdk.database import Database, ModuleDataStore, get_module_base
        from democrai.sdk.dependencies import Dependencies
        from democrai.sdk.effects import Effects
        from democrai.sdk.engines import Engines
        from democrai.sdk.environment import Environment
        from democrai.sdk.events import Events
        from democrai.sdk.extractors import Extractors
        from democrai.sdk.hooks import Hooks
        from democrai.sdk.i18n import I18n
        from democrai.sdk.knowledge import Knowledge
        from democrai.sdk.media import Media
        from democrai.sdk.models import CoreModelsSDK
        from democrai.sdk.module_decorators import Decorators
        from democrai.sdk.pages import Pages
        from democrai.sdk.system import System
        from democrai.sdk.tasks import Tasks
        from democrai.sdk.ui import UI

        from democrai.core.application.session_keys import SessionKey

        user = self.session.get(SessionKey.USER) or {}
        user_id = to_optional_int(user.get("id"))
        if user_id is None:
            debug_log = getattr(getattr(app_ctx(), "logger", None), "debug", None)
            if debug_log is not None:
                debug_log(
                    f"[SDK] No user_id in session for module {module_name}, using anonymous (0)"
                )
            user_id = 0
        organization_id = to_optional_int(user.get("organization_id"))

        store = ModuleDataStore(
            user_id,
            module_name,
            organization_id=organization_id,
            access_level=int(user.get("access_level", 3)),
        )
        self.database = Database(store, get_module_base(module_name))

        self.auth = AuthSDK(self)
        self.models = CoreModelsSDK(self)

        self.ui = UI(self)
        self.effects = Effects(self)
        self.ai = AI(self)
        self.media = Media(self)
        self.extractors = Extractors(self)
        self.knowledge = Knowledge(self)
        self.dependencies = Dependencies()
        self.engines = Engines(self)
        self.environment = Environment()
        self.access = Access(self)
        self.system = System(self)
        self.i18n = I18n(self)
        self.pages = Pages(self)
        self.hooks = Hooks(self)
        self.events = Events(self)
        self.tasks = Tasks(self)
        self.decorators = Decorators(self)


current_sdk: ContextVar[Optional[SDK]] = ContextVar("current_sdk", default=None)

_default_sdk: Optional[SDK] = None


def _get_default_sdk() -> SDK:
    global _default_sdk
    if _default_sdk is None:
        _default_sdk = SDK("", "core")
    return _default_sdk


class SDKProxy:
    """Proxy that resolves attributes from the active request-scoped SDK."""

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the active or default SDK instance."""
        current = current_sdk.get()
        if current is None:
            return getattr(_get_default_sdk(), name)
        return getattr(current, name)


active_sdk = SDKProxy()
