from __future__ import annotations

from typing import Any


def page_state_update(values: dict[str, Any]) -> dict[str, Any]:
    """Wrap store values into a page-scoped stateUpdate UI message."""
    return {
        "stateUpdate": {
            "scope": "page",
            "values": values,
        }
    }


def provider_store_values(
    module_sdk,
    *,
    provider: str,
    status: str,
    activation_ready: bool | None = None,
    activation_message: str | None = None,
) -> dict[str, Any]:
    """Build page store values for the provider status section.

    These drive the reactive visibility of install/activate/deactivate buttons
    via ``bound.store("/provider/status", scope="page")`` in the UI layer.
    """
    normalized_status = str(status or "").strip().lower() or "uninstalled"
    values: dict[str, Any] = {
        "/provider/status": normalized_status,
        "/provider/status_text": module_sdk.i18n.t(
            f"system.engine.status.{normalized_status}"
        ),
    }
    if activation_ready is not None:
        values["/provider/activation_ready"] = bool(activation_ready)
    if activation_message is not None:
        values["/provider/activation_message"] = str(activation_message)
    return values
