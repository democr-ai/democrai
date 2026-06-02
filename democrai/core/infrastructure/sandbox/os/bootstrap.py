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
) -> None:
    asyncio.run(
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
) -> None:
    if getattr(ctx, "setup_mode", False):
        debug_os_sandbox_flow("bootstrap.allowlist_refresh_skipped_setup_mode")
        return

    _apply_process_restrictions(ctx)

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
        return

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


def _apply_process_restrictions(ctx: Any) -> None:
    try:
        from democrai.core.infrastructure.sandbox.os.process_restrictions import (
            apply_process_restrictions,
            is_landlock_enabled,
            is_seccomp_enabled,
        )

        if is_seccomp_enabled(ctx.config) or is_landlock_enabled(ctx.config):
            from democrai.core.infrastructure.sandbox.process_guard import (
                process_guard_bypass_context,
            )

            with process_guard_bypass_context():
                apply_process_restrictions(ctx.config)
    except Exception as exc:
        warnings.warn(f"[Sandbox] process restrictions failed: {exc}")
