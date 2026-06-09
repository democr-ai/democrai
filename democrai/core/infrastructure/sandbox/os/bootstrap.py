from __future__ import annotations

import asyncio
import warnings
from typing import Any

from democrai.core.platform.utils.debug import debug_os_sandbox_flow


def bootstrap_current_process_os_sandbox(
    ctx: Any,
    *,
    reason: str,
    mode: str,
) -> dict[str, Any]:
    return asyncio.run(
        bootstrap_current_process_os_sandbox_async(
            ctx,
            reason=reason,
            mode=mode,
        )
    )


async def bootstrap_current_process_os_sandbox_async(
    ctx: Any,
    *,
    reason: str,
    mode: str,
) -> dict[str, Any]:
    if getattr(ctx, "setup_mode", False):
        debug_os_sandbox_flow("bootstrap.allowlist_refresh_skipped_setup_mode")
        return {"enabled": False, "skipped": "setup_mode"}

    _apply_current_process_os_sandbox(ctx)

    from democrai.core.infrastructure.sandbox.os.events import (
        emit_application_network_allowlist_refresh_event,
        register_os_sandbox_event_listeners,
    )
    from democrai.core.infrastructure.sandbox.os.helper import (
        ensure_os_sandbox_helper_ready,
    )
    from democrai.core.infrastructure.sandbox.os.state import (
        is_application_network_allowlist_enabled,
        set_application_network_allowlist_active,
    )

    enabled = is_application_network_allowlist_enabled(ctx.config)
    set_application_network_allowlist_active(enabled)
    if not enabled:
        debug_os_sandbox_flow("bootstrap.allowlist_refresh_skipped_disabled")
        return {"enabled": False, "skipped": "network_allowlist_disabled"}

    register_os_sandbox_event_listeners()
    ensure_os_sandbox_helper_ready(ctx.config)

    payload = {
        "reason": str(reason or "bootstrap_config_initialized"),
        "resource_type": "",
        "module_name": "",
        "target": "",
        "mode": str(mode or "bootstrap"),
    }
    debug_os_sandbox_flow("bootstrap.allowlist_refresh_emit", payload=payload)
    await emit_application_network_allowlist_refresh_event(payload=payload)
    return {"enabled": True, "payload": payload}


def _apply_current_process_os_sandbox(ctx: Any) -> None:
    enabled = False
    try:
        from democrai.core.infrastructure.sandbox.os.core_relaunch import (
            is_core_os_sandbox_relaunched,
            provider_supports_current_process_os_sandbox,
        )
        from democrai.core.infrastructure.sandbox.os.current_process import (
            apply_current_process_os_sandbox,
            is_os_sandbox_enabled,
        )

        enabled = is_os_sandbox_enabled(ctx.config)
        if enabled:
            if not provider_supports_current_process_os_sandbox():
                if is_core_os_sandbox_relaunched():
                    debug_os_sandbox_flow(
                        "bootstrap.current_process_skipped_launch_only_relaunched"
                    )
                    return
                raise RuntimeError("os_sandbox_core_relaunch_required")
            from democrai.core.infrastructure.sandbox.process_guard import (
                process_guard_bypass_context,
            )

            with process_guard_bypass_context():
                apply_current_process_os_sandbox(ctx.config)
    except Exception as exc:
        if enabled:
            raise
        warnings.warn(f"[Sandbox] current process OS sandbox failed: {exc}")
