from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from democrai.core.runtime.foundation.app import app_ctx


HandlerType = Callable[[Any, Any, Dict[str, Any]], Awaitable[None]]


class ProtocolDispatcher:
    def __init__(self):
        self._handlers: Dict[str, HandlerType] = {}
        self._default_handler: Optional[HandlerType] = None
        self.logger = app_ctx().logger

    def register(self, msg_type: str, handler: HandlerType):
        self._handlers[msg_type] = handler

    def set_default_handler(self, handler: HandlerType):
        self._default_handler = handler

    async def dispatch(self, bus: Any, client_id: Any, msg: Dict[str, Any]):
        for key, handler in self._handlers.items():
            if key in msg:
                try:
                    await handler(bus, client_id, msg)
                    return
                except Exception as e:
                    if self.logger:
                        self.logger.error(
                            f"[Protocol] Error handling key {key}: {e}", exc_info=True
                        )
                    return

        msg_type = msg.get("type")
        if msg_type and msg_type in self._handlers:
            try:
                await self._handlers[msg_type](bus, client_id, msg)
                return
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"[Protocol] Error handling type {msg_type}: {e}",
                        exc_info=True,
                    )
                return

        if self._default_handler:
            await self._default_handler(bus, client_id, msg)
        elif self.logger:
            self.logger.debug(f"[Protocol] No handler for message: {msg.keys()}")
