from __future__ import annotations

from typing import Any, Optional


class Hooks:
    """Expose render-hook discovery and resolution to module code.

    Render hooks let modules contribute UI fragments to named insertion points
    without the caller knowing which module will provide the final components.

    :param sdk: The active SDK instance for the current request.
    """

    def __init__(self, sdk) -> None:
        """Create a render-hook facade for the current SDK instance.

        :param sdk: The active SDK instance.
        """
        self.sdk = sdk

    def qualify_render_hook_name(self, name: str) -> str:
        """Return a fully qualified render-hook name for the current module.

        :param name: Raw or already qualified render-hook name.
        :return: Fully qualified render-hook name.
        """
        if not isinstance(name, str):
            return str(name)
        hook_name = name.strip()
        if not hook_name:
            return hook_name
        if self.sdk.module_name == "core" or hook_name.startswith(f"{self.sdk.module_name}."):
            return hook_name
        return f"{self.sdk.module_name}.{hook_name}"

    def get_render_hook_slots(self, module_name: Optional[str] = None):
        """Return the render-hook slots declared in the runtime registry.

        :param module_name: Optional module-name filter.
        :return: The registry definitions returned by ``render_hook_registry``.
        """
        from democrai.core.runtime.foundation.registry import render_hook_registry

        return render_hook_registry.get_definitions(module_name or None)

    async def resolve_render_hook(
        self,
        name: str,
        *,
        params: Optional[dict[str, Any]] = None,
        session: Optional[dict] = None,
    ):
        """Resolve the components contributed to a render hook.

        The method qualifies the hook name, then asks the render-hook runtime to
        build the components contributed by listeners for that hook.

        :param name: Render-hook name, raw or fully qualified.
        :param params: Optional parameters passed to hook resolvers.
        :param session: Optional explicit session override. When omitted, the
            current SDK session is used.
        :return: The resolved components returned by the hook runtime.
        """
        from democrai.core.platform.ui.hooks import resolve_render_hook_components

        return await resolve_render_hook_components(
            self.qualify_render_hook_name(name),
            params=params if params is not None else {},
            session=session if session is not None else self.sdk.session,
        )
