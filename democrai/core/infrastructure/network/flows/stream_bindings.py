from __future__ import annotations

import asyncio
import copy
from typing import Any

from democrai.core.application.auth.service import get_user_permissions
from democrai.core.application.handler.action_resolution import resolve_module_name
from democrai.core.application.session_keys import SessionKey
from democrai.core.runtime.foundation.app import app_ctx, req_ctx
from democrai.sdk.client import SDK

_SUPPORTED_MODES = {"set", "append_window"}


def _binding_key(bus: Any, client_id: Any, binding_id: str) -> tuple[int, Any, str]:
    return (id(bus), client_id, str(binding_id or "").strip())


def _canonical_subscribe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    target = payload.get("target")
    transformer = payload.get("transformer")
    return {
        "bindingId": str(
            payload.get("bindingId") or payload.get("binding_id") or ""
        ).strip(),
        "stream": str(payload.get("stream") or payload.get("sourceStream") or "").strip(),
        "event": str(payload.get("event") or payload.get("eventName") or "").strip(),
        "target": copy.deepcopy(target) if isinstance(target, dict) else {},
        "transformer": _normalize_transformer(transformer),
    }


def _normalize_transformer(transformer: Any) -> dict[str, Any]:
    if isinstance(transformer, str):
        name = transformer.strip()
        return {"name": name} if name else {}
    if isinstance(transformer, dict):
        normalized = copy.deepcopy(transformer)
        name = str(normalized.get("name") or "").strip()
        if not name:
            return {}
        normalized["name"] = name
        context = normalized.get("context")
        if context is not None and not isinstance(context, dict):
            raise ValueError("transformer.context must be a dict")
        return normalized
    return {}


def _normalize_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    return text if text.startswith("/") else f"/{text}"


def _extract_path(payload: Any, expression: Any) -> Any:
    if not isinstance(expression, str):
        return expression
    text = expression.strip()
    if not text.startswith("$."):
        raise ValueError(f"invalid_selector:{text}")
    current = payload
    for part in text[2:].split("."):
        if not part:
            raise ValueError(f"invalid_selector:{text}")
        if isinstance(current, dict):
            current = current.get(part)
            continue
        raise ValueError(f"selector_not_found:{text}")
    return current


def _event_matches(payload: Any, event_name: str) -> bool:
    if not event_name:
        return True
    if not isinstance(payload, dict):
        return False
    return str(payload.get("event_name") or "").strip() == event_name


def _build_values(
    payload: dict[str, Any],
    *,
    path: str,
    mode: str,
    mappings: dict[str, Any],
    window: int,
    series: dict[str, list[Any]],
) -> dict[str, Any]:
    if mode not in _SUPPORTED_MODES:
        raise ValueError(f"unsupported_mode:{mode}")
    values: dict[str, Any] = {}
    if mode == "append_window":
        limit = max(1, int(window or 60))
        for key, expression in mappings.items():
            field = str(key or "").strip()
            if not field:
                continue
            current = series.setdefault(field, [])
            current.append(_extract_path(payload, expression))
            if len(current) > limit:
                del current[: len(current) - limit]
            values[f"{path}/{field}"] = list(current)
        return values

    for key, expression in mappings.items():
        field = str(key or "").strip()
        if field:
            values[f"{path}/{field}"] = _extract_path(payload, expression)
    return values


async def _run_transformer(
    network: Any,
    *,
    transformer: dict[str, Any],
    payload: dict[str, Any],
    binding_id: str,
    source_stream: str,
    target_stream: str,
    event_name: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    action_name = str(transformer.get("name") or "").strip()
    if not action_name:
        raise ValueError("transformer.name is required")

    current = req_ctx()
    session = network.core.get_session(
        current.user,
        current.role,
        session_key=current.session_key,
    )
    permissions = (
        get_user_permissions(current.user) if current.user is not None else []
    )
    sdk = SDK(
        "",
        "core",
        current_path=str(session.get(SessionKey.CURRENT_PATH, "") or ""),
        session=session,
    )
    user_context = transformer.get("context")
    action_ctx = {
        "stream_id": target_stream,
        "binding_id": binding_id,
        "source_stream": source_stream,
        "event": event_name,
        "payload": copy.deepcopy(payload),
        "target": copy.deepcopy(target),
        "context": copy.deepcopy(user_context) if isinstance(user_context, dict) else {},
    }

    previous_action = current.action_name
    previous_module = current.module_name
    previous_stream = current.stream_id
    current.action_name = action_name
    current.module_name = resolve_module_name(action_name) or "core"
    current.stream_id = target_stream
    try:
        result = await network.core.dispatcher.dispatch(
            action_name,
            action_ctx,
            session,
            permissions,
            sdk,
        )
    finally:
        current.action_name = previous_action
        current.module_name = previous_module
        current.stream_id = previous_stream

    if isinstance(result, dict) and result.get("type") == "error":
        raise ValueError(f"transformer_failed:{result.get('error') or action_name}")
    return result if isinstance(result, dict) else {"value": result}


def _build_transformer_values(
    result: dict[str, Any],
    *,
    target_path: str,
) -> dict[str, Any]:
    explicit_values = result.get("values")
    if isinstance(explicit_values, dict):
        values: dict[str, Any] = {}
        for path, value in explicit_values.items():
            normalized_path = _normalize_path(path)
            if normalized_path:
                values[normalized_path] = value
        return values
    if "value" not in result:
        raise ValueError("transformer result must contain value or values")
    if not target_path:
        raise ValueError("target.path is required for transformer value")
    return {target_path: result["value"]}


async def _run_stream_binding(
    network: Any,
    *,
    binding_id: str,
    source_stream: str,
    target_stream: str,
    event_name: str,
    target: dict[str, Any],
    transformer: dict[str, Any],
) -> None:
    queue = network.stream_manager.subscribe(source_stream)
    mode = str(target.get("mode") or "set").strip().lower()
    if not transformer and mode not in _SUPPORTED_MODES:
        raise ValueError(f"unsupported_mode:{mode}")
    path = _normalize_path(str(target.get("path") or ""))
    scope = str(target.get("store") or target.get("scope") or "page").strip().lower()
    mappings = target.get("mappings")
    if not transformer and not isinstance(mappings, dict):
        raise ValueError("target.mappings must be a dict")
    if not transformer and not path:
        raise ValueError("target.path is required")
    window = int(target.get("window") or 60)
    series: dict[str, list[Any]] = {}

    try:
        while True:
            payload = await queue.get()
            if not _event_matches(payload, event_name):
                continue
            if not isinstance(payload, dict):
                continue
            if transformer:
                result = await _run_transformer(
                    network,
                    transformer=transformer,
                    payload=payload,
                    binding_id=binding_id,
                    source_stream=source_stream,
                    target_stream=target_stream,
                    event_name=event_name,
                    target=target,
                )
                values = _build_transformer_values(result, target_path=path)
            else:
                if not path or not mappings:
                    continue
                values = _build_values(
                    payload,
                    path=path,
                    mode=mode,
                    mappings=mappings,
                    window=window,
                    series=series,
                )
            if values:
                await network.stream_manager.broadcast(
                    target_stream,
                    {
                        "stateUpdate": {
                            "scope": "global" if scope == "global" else "page",
                            "values": values,
                        }
                    },
                )
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.error(
                f"[StreamBinding] binding failed id={binding_id} stream={source_stream}: {exc}"
            )
    finally:
        network.stream_manager.unsubscribe(source_stream, queue)


def _cancel_binding(network: Any, key: tuple[int, Any, str]) -> None:
    task = network._stream_bindings.pop(key, None)
    if task is not None:
        task.cancel()


async def handle_stream_binding_subscribe(network: Any, bus: Any, client_id: Any, msg: dict) -> None:
    ctx = req_ctx()
    if ctx.user is None:
        network._send_auth_error(bus, client_id, msg, "authentication_required")
        return
    stream_id = network._authorize_and_bind_stream(
        bus,
        client_id,
        msg,
        ctx,
        reject_on_unauthenticated=True,
    )
    if stream_id is None:
        return

    payload = msg.get("streamBindingSubscribe")
    if not isinstance(payload, dict):
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.warning("[StreamBinding] invalid subscribe payload")
        return
    spec = _canonical_subscribe_payload(payload)
    binding_id = spec["bindingId"]
    source_stream = spec["stream"]
    target = spec["target"]
    if not binding_id or not source_stream or not isinstance(target, dict):
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.warning(
                "[StreamBinding] malformed subscribe "
                f"binding_id={binding_id!r} stream={source_stream!r} "
                f"target_type={type(target).__name__}"
            )
        return

    key = _binding_key(bus, client_id, binding_id)
    if network._stream_binding_specs.get(key) != spec:
        network._send_auth_error(bus, client_id, msg, "stream_binding_not_allowed")
        return

    _cancel_binding(network, key)
    task = asyncio.create_task(
        _run_stream_binding(
            network,
            binding_id=binding_id,
            source_stream=source_stream,
            target_stream=stream_id,
            event_name=spec["event"],
            target=dict(target),
            transformer=dict(spec["transformer"]),
        )
    )
    network._stream_bindings[key] = task


async def handle_stream_binding_unsubscribe(network: Any, bus: Any, client_id: Any, msg: dict) -> None:
    ctx = req_ctx()
    if ctx.user is None:
        return
    payload = msg.get("streamBindingUnsubscribe")
    if not isinstance(payload, dict):
        return
    binding_id = str(payload.get("bindingId") or payload.get("binding_id") or "").strip()
    if not binding_id:
        return
    _cancel_binding(network, _binding_key(bus, client_id, binding_id))


def cleanup_stream_bindings(network: Any, bus: Any, client_id: Any) -> None:
    prefix = (id(bus), client_id)
    for key in [key for key in network._stream_bindings if key[:2] == prefix]:
        _cancel_binding(network, key)
    for key in [key for key in network._stream_binding_specs if key[:2] == prefix]:
        network._stream_binding_specs.pop(key, None)


def register_stream_bindings_from_message(
    network: Any,
    bus: Any,
    client_id: Any,
    message: Any,
) -> None:
    if isinstance(message, list):
        for item in message:
            register_stream_bindings_from_message(network, bus, client_id, item)
        return
    if not isinstance(message, dict):
        return
    if isinstance(message.get("messages"), list):
        register_stream_bindings_from_message(
            network,
            bus,
            client_id,
            message["messages"],
        )

    update = message.get("surfaceUpdate") or message.get("surface_update")
    if not isinstance(update, dict):
        return
    components = update.get("components")
    if not isinstance(components, list):
        return
    for component in components:
        if not isinstance(component, dict):
            continue
        binding_id = str(component.get("id") or "").strip()
        component_body = component.get("component")
        if not binding_id or not isinstance(component_body, dict):
            continue
        props = component_body.get("StreamBinding")
        if not isinstance(props, dict):
            continue
        spec = _canonical_subscribe_payload(
            {
                "bindingId": binding_id,
                "stream": props.get("stream"),
                "event": props.get("event"),
                "target": props.get("target"),
                "transformer": props.get("transformer"),
            }
        )
        if spec["stream"] and spec["target"]:
            network._stream_binding_specs[_binding_key(bus, client_id, binding_id)] = spec
