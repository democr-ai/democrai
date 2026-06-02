from __future__ import annotations

from typing import Any, Optional


class Events:
    """Expose the module event system through a safe SDK facade.

    Modules should use this class when they need to qualify event names, inspect
    declared event slots, or emit application events without importing the lower
    level event runtime directly.

    :param sdk: The active SDK instance for the current module request.
    """

    def __init__(self, sdk) -> None:
        """Create an event facade bound to the current SDK instance.

        :param sdk: The active SDK instance.
        """
        self.sdk = sdk

    def qualify_event_name(self, name: str) -> str:
        """Return a fully qualified event name for the current module.

        If the provided name is already qualified with the current module prefix
        or the current module is ``core``, the name is returned unchanged.
        Otherwise the method prefixes the name with ``<module_name>.``.

        :param name: Raw or already qualified event name.
        :return: Fully qualified event name.
        """
        if not isinstance(name, str):
            return str(name)
        event_name = name.strip()
        if not event_name:
            return event_name
        if self.sdk.module_name == "core" or event_name.startswith(f"{self.sdk.module_name}."):
            return event_name
        return f"{self.sdk.module_name}.{event_name}"

    def get_event_slots(self, module_name: Optional[str] = None):
        """Return the event-slot definitions registered in the runtime.

        :param module_name: Optional module name filter. When omitted, the
            runtime returns all known event-slot definitions.
        :return: The registry definitions returned by ``module_event_registry``.
        """
        from democrai.core.runtime.foundation.registry import module_event_registry

        return module_event_registry.get_definitions(module_name or None)

    async def emit(
        self,
        name: str,
        *,
        payload: Optional[dict[str, Any]] = None,
        session: Optional[dict] = None,
    ):
        """Emit a module event using the qualified event name.

        The method qualifies the provided name using the current module prefix
        and forwards the emission to the shared runtime event dispatcher.

        :param name: Event name, raw or fully qualified.
        :param payload: Optional event payload delivered to listeners.
        :param session: Optional explicit session override. When omitted, the
            current SDK session is used.
        :return: The result returned by the event dispatcher.
        """
        from democrai.core.platform.events import emit_module_event

        return await emit_module_event(
            self.qualify_event_name(name),
            payload=payload,
            session=session if session is not None else self.sdk.session,
        )

    def subscribe_stream(self, stream_id: str):
        """Subscribe to a runtime stream and return its queue."""
        from democrai.core.runtime.foundation.app import app_ctx

        network = getattr(app_ctx(), "network", None)
        stream_manager = getattr(network, "stream_manager", None)
        if stream_manager is None:
            raise RuntimeError("stream_manager_unavailable")
        return stream_manager.subscribe(str(stream_id or "").strip())

    def unsubscribe_stream(self, stream_id: str, queue) -> None:
        """Unsubscribe a queue previously returned by ``subscribe_stream``."""
        from democrai.core.runtime.foundation.app import app_ctx

        network = getattr(app_ctx(), "network", None)
        stream_manager = getattr(network, "stream_manager", None)
        if stream_manager is None:
            return
        stream_manager.unsubscribe(str(stream_id or "").strip(), queue)
