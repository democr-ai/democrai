from __future__ import annotations
from typing import Any, Dict, List

from democrai.core.infrastructure.database.session_store import SessionStore
from democrai.core.application.request_cycle import RequestCycleEngine, RequestEnvelope
from democrai.core.application.session import SessionService
from democrai.core.platform.ui import RenderService
from democrai.core.runtime.foundation.app import req_ctx

from democrai.core.application.handler.dispatcher import ActionDispatcher


class Core:
    def __init__(self):
        self.session_store = SessionStore()
        self.session_service = SessionService(self.session_store)
        self.render_service = RenderService(self.session_service)
        self.dispatcher = ActionDispatcher()
        self.request_engine = RequestCycleEngine()

    def get_session(
        self,
        user: str | None,
        role: str | None = None,
        session_key: str | None = None,
    ) -> dict:
        resolved_session_key = session_key
        if resolved_session_key is None:
            try:
                resolved_session_key = req_ctx().session_key
            except Exception:
                resolved_session_key = None
        if resolved_session_key is None:
            return self.session_service.get_or_create(user, role)
        return self.session_service.get_or_create(
            user, role, session_key=resolved_session_key
        )

    def reset_session_store(self) -> None:
        self.session_store = SessionStore()
        self.session_service = SessionService(self.session_store)
        self.render_service = RenderService(self.session_service)

    async def render(self, session: dict, force_shell: bool = False) -> List[Dict[str, Any]]:
        return await self.render_service.render(session, force_shell=force_shell)

    async def handle(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        envelope = msg if isinstance(msg, RequestEnvelope) else RequestEnvelope.from_message(msg)
        return await self.request_engine.handle(
            envelope,
            get_session=self.get_session,
            render=self.render,
            dispatcher=self.dispatcher,
            session_service=self.session_service,
        )
