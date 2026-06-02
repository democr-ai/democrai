from __future__ import annotations

import inspect
import os
from typing import Any

from democrai.core.platform.utils.normalize import normalize_bool


def _env_enabled(env_name: str) -> bool:
    return normalize_bool(os.getenv(env_name), default=False)


def _caller_fields() -> dict[str, object]:
    stack = inspect.stack(context=0)
    try:
        for frame_info in stack[2:]:
            raw_filename = getattr(frame_info, "filename", None)
            filename = raw_filename if isinstance(raw_filename, str) else ""
            if filename == __file__:
                continue
            try:
                module = inspect.getmodule(getattr(frame_info, "frame", None))
            except Exception:
                module = None
            if getattr(module, "__name__", "") == __name__:
                continue
            raw_function = getattr(frame_info, "function", None)
            function_name = raw_function if isinstance(raw_function, str) else ""
            raw_lineno = getattr(frame_info, "lineno", None)
            line_number = raw_lineno if isinstance(raw_lineno, int) else 0
            return {
                "caller_file": filename,
                "caller_function": function_name,
                "caller_line": line_number,
            }
    except Exception:
        return {
            "caller_file": "",
            "caller_function": "",
            "caller_line": 0,
        }
    finally:
        del stack
    return {
        "caller_file": "",
        "caller_function": "",
        "caller_line": 0,
    }


def _emit_debug(
    *,
    env_name: str,
    tag: str,
    event: str,
    always_for_setup: bool = False,
    **fields: Any,
) -> None:
    raw_current_path = fields.get("current_path")
    current_path = raw_current_path if isinstance(raw_current_path, str) else ""
    if not _env_enabled(env_name):
        if not (always_for_setup and current_path == "/system/setup"):
            return
    merged_fields = {
        **_caller_fields(),
        **fields,
    }
    details = " ".join(f"{key}={value!r}" for key, value in merged_fields.items())
    event_name = event.strip() if isinstance(event, str) else ""
    print(f"[{tag}] {event_name}" + (f" {details}" if details else ""), flush=True)


def debug_media_flow(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_MEDIA_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_MEDIA_FLOW", tag="MEDIA_FLOW", event=event, **fields)


def debug_auth_flow(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_AUTH_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_AUTH_FLOW", tag="AUTH_FLOW", event=event, **fields)


def debug_desktop_trace(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_UI_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_UI_FLOW", tag="DESKTOP_TRACE", event=event, **fields)


def debug_image_switch(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_IMAGE_SWITCH=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_IMAGE_SWITCH", tag="IMAGE_SWITCH", event=event, **fields)


def debug_property_trace(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_UI_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_UI_FLOW", tag="PROPERTY_TRACE", event=event, **fields)


def debug_surface_trace(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_UI_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_UI_FLOW", tag="SURFACE_TRACE", event=event, **fields)


def debug_renderer_trace(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_UI_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_UI_FLOW", tag="RENDERER_TRACE", event=event, **fields)


def debug_session_trace(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_UI_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_UI_FLOW", tag="SESSION_TRACE", event=event, **fields)


def debug_ui_trace(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_UI_FLOW=1. Also prints for current_path=/system/setup."""
    _emit_debug(
        env_name="DEMOCRAI_DEBUG_UI_FLOW",
        tag="UI_TRACE",
        event=event,
        always_for_setup=True,
        **fields,
    )


def debug_ipc_trace(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_UI_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_UI_FLOW", tag="IPC_TRACE", event=event, **fields)


def debug_token_store(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_AUTH_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_AUTH_FLOW", tag="TOKEN_STORE", event=event, **fields)


def debug_runtime_shutdown(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_AUTH_FLOW=1"""
    _emit_debug(env_name="DEMOCRAI_DEBUG_AUTH_FLOW", tag="DESKTOP_SHUTDOWN", event=event, **fields)


def debug_attachment_preview(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_ATTACHMENT_PREVIEW=1"""
    _emit_debug(
        env_name="DEMOCRAI_DEBUG_ATTACHMENT_PREVIEW",
        tag="ATTACHMENT_PREVIEW",
        event=event,
        **fields,
    )


def debug_os_sandbox_flow(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_OS_SANDBOX_FLOW=1"""
    _emit_debug(
        env_name="DEMOCRAI_DEBUG_OS_SANDBOX_FLOW",
        tag="OS_SANDBOX_FLOW",
        event=event,
        **fields,
    )


def debug_engine_install_flow(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_ENGINE_INSTALL_FLOW=1"""
    _emit_debug(
        env_name="DEMOCRAI_DEBUG_ENGINE_INSTALL_FLOW",
        tag="ENGINE_INSTALL_FLOW",
        event=event,
        **fields,
    )


def debug_request_context_flow(event: str, **fields: Any) -> None:
    """Env: DEMOCRAI_DEBUG_REQUEST_CONTEXT_FLOW=1"""
    _emit_debug(
        env_name="DEMOCRAI_DEBUG_REQUEST_CONTEXT_FLOW",
        tag="REQUEST_CONTEXT_FLOW",
        event=event,
        **fields,
    )
