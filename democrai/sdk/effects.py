from __future__ import annotations

from typing import Any, Optional


class Effects:
    """Build and publish client-visible effects for UI and runtime actions."""

    def __init__(self, sdk) -> None:
        """Bind the effects facade to the current SDK instance."""
        self.sdk = sdk

    async def publish_to_stream(self, stream_id: str, data: Any):
        """Broadcast arbitrary data to a runtime stream."""
        from democrai.core.runtime.foundation.app import app_ctx

        await app_ctx().network.stream_manager.broadcast(stream_id, data)

    async def publish_ui_message(self, stream_id: str, message: dict[str, Any]):
        """Broadcast a pre-built UI protocol message to a stream."""
        await self.publish_to_stream(stream_id, message)

    async def ask_client(
        self,
        stream_id: str | None,
        query: dict[str, Any],
        *,
        timeout: float = 5.0,
    ) -> Any:
        """Ask the client that owns a stream for current runtime UI state."""
        from democrai.core.runtime.foundation.app import app_ctx, req_ctx

        resolved_stream_id = str(stream_id or "").strip()
        if not resolved_stream_id:
            try:
                resolved_stream_id = str(req_ctx().stream_id or "").strip()
            except LookupError:
                resolved_stream_id = ""
        if not resolved_stream_id:
            raise ValueError("stream_id is required")

        network = getattr(app_ctx(), "network", None)
        ask = getattr(network, "ask_client", None)
        if not callable(ask):
            raise RuntimeError("client query runtime is not available")
        return await ask(resolved_stream_id, query, timeout=timeout)

    async def ask_current_store_value(
        self,
        stream_id: str | None,
        store_key: str,
        store_type: str = "auto",
        *,
        timeout: float = 5.0,
    ) -> Any:
        """Read the current page/global store value held by the client."""
        return await self.ask_client(
            stream_id,
            {
                "kind": "store_value",
                "path": str(store_key or ""),
                "scope": str(store_type or "auto"),
            },
            timeout=timeout,
        )

    async def ask_current_data_value(
        self,
        stream_id: str | None,
        path: str,
        *,
        surface_id: str = "main",
        timeout: float = 5.0,
    ) -> Any:
        """Read the current surface data-model value held by the client."""
        return await self.ask_client(
            stream_id,
            {
                "kind": "data_value",
                "surfaceId": str(surface_id or "main"),
                "path": str(path or ""),
            },
            timeout=timeout,
        )

    async def ask_current_component_props(
        self,
        stream_id: str | None,
        component_id: str,
        *,
        surface_id: str = "main",
        timeout: float = 5.0,
    ) -> Any:
        """Read the current protocol props for a component from the client tree."""
        return await self.ask_client(
            stream_id,
            {
                "kind": "component_props",
                "surfaceId": str(surface_id or "main"),
                "componentId": str(component_id or ""),
            },
            timeout=timeout,
        )

    async def ask_current_component(
        self,
        stream_id: str | None,
        component_id: str,
        *,
        surface_id: str = "main",
        timeout: float = 5.0,
    ) -> Any:
        """Read the current protocol component node from the client tree."""
        return await self.ask_client(
            stream_id,
            {
                "kind": "component",
                "surfaceId": str(surface_id or "main"),
                "componentId": str(component_id or ""),
            },
            timeout=timeout,
        )

    async def ask_current_surface_tree(
        self,
        stream_id: str | None,
        *,
        surface_id: str = "main",
        timeout: float = 5.0,
    ) -> Any:
        """Read the current protocol surface tree held by the client."""
        return await self.ask_client(
            stream_id,
            {
                "kind": "surface_tree",
                "surfaceId": str(surface_id or "main"),
            },
            timeout=timeout,
        )

    async def publish_property_update(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        action: str = "set",
        surface_id: str = "main",
    ):
        """Publish a property update for a component through a live stream."""
        await self.publish_ui_message(
            stream_id,
            self.sdk.ui.Builder.build_property_update_payload(
                component_id=component_id,
                property_name=property_name,
                value=value,
                action=action,
                surface_id=surface_id,
            ),
        )

    async def publish_collection_append(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ):
        """Publish a collection append update to a live stream."""
        await self.publish_ui_message(
            stream_id,
            self.sdk.ui.Builder.build_collection_append_payload(
                component_id=component_id,
                property_name=property_name,
                value=value,
                surface_id=surface_id,
            ),
        )

    async def publish_collection_prepend(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ):
        """Publish a collection prepend update to a live stream."""
        await self.publish_ui_message(
            stream_id,
            self.sdk.ui.Builder.build_collection_prepend_payload(
                component_id=component_id,
                property_name=property_name,
                value=value,
                surface_id=surface_id,
            ),
        )

    async def publish_state_patch(
        self,
        stream_id: str,
        path: str,
        action: str,
        value: Any,
        *,
        scope: str = "page",
    ):
        """Publish a collection patch for page/global client store."""
        await self.publish_ui_message(
            stream_id,
            self.sdk.ui.Builder.build_state_patch_payload(
                path=path,
                action=action,
                value=value,
                scope=scope,
            ),
        )

    async def publish_collection_remove(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ):
        """Publish a collection remove update to a live stream."""
        await self.publish_ui_message(
            stream_id,
            self.sdk.ui.Builder.build_collection_remove_payload(
                component_id=component_id,
                property_name=property_name,
                value=value,
                surface_id=surface_id,
            ),
        )

    async def publish_collection_replace(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ):
        """Publish a collection replace update to a live stream."""
        await self.publish_ui_message(
            stream_id,
            self.sdk.ui.Builder.build_collection_replace_payload(
                component_id=component_id,
                property_name=property_name,
                value=value,
                surface_id=surface_id,
            ),
        )

    def navigate(self, path: str, render: bool = True) -> dict[str, Any]:
        """Build a navigation effect payload."""
        return {"type": "navigate", "path": path, "render": render}

    def render(self, path: Optional[str] = None) -> dict[str, Any]:
        """Build a render effect payload for the current or explicit path."""
        effect = {"type": "render"}
        if path:
            effect["path"] = path
        return effect

    def ui_messages(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Wrap raw UI protocol messages into one effect payload."""
        return {"type": "ui_messages", "messages": messages}

    def build_aux_surface_messages(
        self, builder: Any, surface_id: str
    ) -> list[dict[str, Any]]:
        """Build messages required to render an auxiliary surface (drawer/modal)."""
        root_ids = [component.id for component in builder.get_roots() if component.id]
        if not root_ids:
            return [{"deleteSurface": {"surfaceId": surface_id}}]

        if len(root_ids) > 1:
            wrapper = builder.__class__()
            wrapper.merge(builder, components=True, replace=True)
            wrapper.add(self.sdk.ui.Column(f"{surface_id}_root", root_ids))
            builder = wrapper
            root_ids = [f"{surface_id}_root"]

        messages = list(builder.build_surface_update_payload(surface_id))
        data_model = getattr(builder, "_data_model", None)
        if isinstance(data_model, dict) and data_model:
            messages.append(
                builder.__class__.build_data_model_update_payload(
                    surface_id=surface_id,
                    data=data_model,
                )
            )
        store_data = getattr(builder, "_store_data", None)
        if isinstance(store_data, dict):
            for scope in ("page", "global"):
                values = store_data.get(scope)
                if isinstance(values, dict) and values:
                    messages.append(
                        builder.__class__.build_state_update_payload(
                            values,
                            scope=scope,
                        )
                    )
        messages.append(
            {"beginRendering": {"root": root_ids[0], "surfaceId": surface_id}}
        )
        return messages

    def ui_agent_commands(self, commands: list[dict[str, Any]]) -> dict[str, Any]:
        """Build an agent UI command payload."""
        return {"agentUICommands": {"commands": commands}}

    def ui_property_update(
        self,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        action: str = "set",
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a property update protocol payload."""
        return self.sdk.ui.Builder.build_property_update_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            action=action,
            surface_id=surface_id,
        )

    def ui_collection_append(
        self,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a collection append protocol payload."""
        return self.sdk.ui.Builder.build_collection_append_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            surface_id=surface_id,
        )

    def ui_collection_prepend(
        self,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a collection prepend protocol payload."""
        return self.sdk.ui.Builder.build_collection_prepend_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            surface_id=surface_id,
        )

    def ui_state_patch(
        self,
        path: str,
        action: str,
        value: Any,
        *,
        scope: str = "page",
    ) -> dict[str, Any]:
        """Build a page/global client store collection patch payload."""
        return self.sdk.ui.Builder.build_state_patch_payload(
            path=path,
            action=action,
            value=value,
            scope=scope,
        )

    def ui_collection_remove(
        self,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a collection remove protocol payload."""
        return self.sdk.ui.Builder.build_collection_remove_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            surface_id=surface_id,
        )

    def ui_collection_replace(
        self,
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a collection replace protocol payload."""
        return self.sdk.ui.Builder.build_collection_replace_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            surface_id=surface_id,
        )

    def pipeline(
        self,
        task: Any,
        label: str,
        args: Optional[dict[str, Any]] = None,
        module: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a pipeline execution effect payload."""
        return {
            "type": "pipeline",
            "task": task,
            "label": label,
            "args": args if args is not None else {},
            "module": module if module is not None else self.sdk.module_name,
        }

    def confirm(
        self,
        *,
        via: str = "dialog",
        path: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
        render: bool = True,
    ) -> dict[str, Any]:
        """Build a confirmation effect payload."""
        return {
            "type": "confirm",
            "via": via,
            "path": path,
            "params": params if params is not None else {},
            "render": render,
        }

    def notify(
        self,
        channel: str,
        payload: dict[str, Any],
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Build a notification effect payload."""
        return {
            "type": "notify",
            "channel": channel,
            "payload": payload,
            "user_id": user_id,
            "organization_id": organization_id,
        }

    def scroll(self, component_id: str) -> dict[str, Any]:
        """Build an effect that requests scrolling to a component."""
        return {"type": "scroll", "component_id": component_id}

    def refresh_modules(self) -> dict[str, Any]:
        """Build an effect that asks the client/runtime to refresh modules."""
        return {"type": "refresh_modules"}

    def set_jwt(self, token: str) -> dict[str, Any]:
        """Build an effect that replaces the client JWT token."""
        return {"type": "set_jwt", "token": token}

    def copy_to_clipboard(self, text: str) -> dict[str, Any]:
        """Build a window action that copies text to the clipboard."""
        return {"type": "window_action", "op": "copy_to_clipboard", "text": text}

    def open_url(
        self,
        url: str,
        *,
        download: bool = False,
        filename: str = "",
    ) -> dict[str, Any]:
        """Build a window action that opens a URL or triggers a download."""
        return {
            "type": "window_action",
            "op": "open_url",
            "url": url,
            "download": download,
            "filename": filename,
        }

    def _serialize_effect(self, effect: Any) -> Any:
        """Recursively serialize nested SDK values inside an effect payload."""
        from democrai.sdk.components.base import Component

        if isinstance(effect, Component):
            return effect.to_dict()
        if isinstance(effect, dict):
            return {key: self._serialize_effect(value) for key, value in effect.items()}
        if isinstance(effect, (list, tuple)):
            return [self._serialize_effect(value) for value in effect]
        return effect

    def respond(self, *effects: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Wrap one or more effects into the standard action response payload."""
        serialized_effects: list[dict[str, Any]] = []
        for effect in effects:
            if isinstance(effect, dict):
                serialized_effects.append(self._serialize_effect(effect))
        return {"effects": serialized_effects}
