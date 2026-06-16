from __future__ import annotations

from typing import Any, Callable, Dict

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from democrai.core.application.session import generate_session_key
from democrai.core.platform.utils.identity import to_optional_int


def register_auth_session_routes(
    app: FastAPI,
    *,
    decode_token_if_present: Callable[[str | None], dict | None],
    decode_token_claims_unverified: Callable[[str | None], dict | None],
    resolve_request_token: Callable[[Request], str | None],
    auth_payload_to_response: Callable[[dict | None], dict[str, Any]],
    set_session_cookie: Callable[[JSONResponse, str], None],
    clear_auth_cookie: Callable[[JSONResponse], None],
    set_auth_cookie: Callable[[JSONResponse, str], None],
    resolve_client_ip: Callable[[Any, Any], str | None],
    observability_service: Any,
    session_cookie_name: Callable[[], str],
    delete_session_by_key: Callable[[str], None] | None = None,
) -> None:
    def _delete_session_for_request(request: Request) -> None:
        if not callable(delete_session_by_key):
            return
        current_session_key = str(
            getattr(request, "cookies", {}).get(session_cookie_name()) or ""
        ).strip()
        if not current_session_key:
            return
        try:
            delete_session_by_key(current_session_key)
        except Exception as exc:
            observability_service.record_auth_event(
                event_type="auth.session.cleanup_error",
                subject_user_id=None,
                success=False,
                metadata={
                    "reason": "session_delete_failed",
                    "session_key": current_session_key,
                    "error": str(exc),
                    "client_ip": resolve_client_ip(
                        request.headers, getattr(request, "client", None)
                    ),
                },
            )

    @app.get("/auth/session")
    async def auth_session_status(request: Request):
        token = resolve_request_token(request)
        payload = decode_token_if_present(token)
        if token and payload is None:
            # Token present but invalid/expired — force logout
            _delete_session_for_request(request)
            unverified = decode_token_claims_unverified(token)
            user_id = to_optional_int(unverified.get("user_id")) if unverified else None
            response = JSONResponse(auth_payload_to_response(None), status_code=401)
            clear_auth_cookie(response)
            set_session_cookie(response, generate_session_key())
            observability_service.record_auth_event(
                event_type="auth.session.expired",
                subject_user_id=user_id,
                success=True,
                metadata={
                    "client_ip": resolve_client_ip(
                        request.headers, getattr(request, "client", None)
                    )
                },
            )
            return response
        response_payload = auth_payload_to_response(payload)
        if payload and token:
            response_payload["jwt"] = token
        response = JSONResponse(response_payload)
        if not request.cookies.get(session_cookie_name()):
            set_session_cookie(response, generate_session_key())
        return response

    @app.post("/auth/session")
    async def auth_session_set(body: Dict[str, Any], request: Request):
        token = str(body.get("jwt") or "").strip()
        current_session_key = str(
            getattr(request, "cookies", {}).get(session_cookie_name()) or ""
        ).strip()
        payload = decode_token_if_present(token)
        user_id = to_optional_int(payload.get("user_id")) if payload else None
        if not payload or user_id is None:
            observability_service.record_auth_event(
                event_type="auth.session.set",
                subject_user_id=None,
                success=False,
                metadata={
                    "reason": "invalid_or_expired_token",
                    "client_ip": resolve_client_ip(
                        request.headers, getattr(request, "client", None)
                    ),
                },
            )
            response = JSONResponse(
                {
                    "authenticated": False,
                    "user": None,
                    "role": "Guest",
                    "permissions": [],
                    "organization_id": None,
                    "access_level": None,
                    "error": "invalid_or_expired_token",
                },
                status_code=401,
            )
            clear_auth_cookie(response)
            set_session_cookie(
                response,
                current_session_key or generate_session_key(),
            )
            return response

        response_payload = auth_payload_to_response(payload)
        response_payload["jwt"] = token
        response = JSONResponse(response_payload)
        set_auth_cookie(response, token)
        set_session_cookie(
            response,
            current_session_key or generate_session_key(),
        )
        observability_service.record_auth_event(
            event_type="auth.session.set",
            subject_user_id=user_id,
            success=True,
            metadata={
                "role": payload.get("role"),
                "organization_id": payload.get("organization_id"),
                "access_level": payload.get("access_level"),
                "client_ip": resolve_client_ip(
                    request.headers, getattr(request, "client", None)
                ),
            },
        )
        return response

    @app.delete("/auth/session")
    async def auth_session_clear(request: Request):
        _delete_session_for_request(request)
        payload = decode_token_if_present(resolve_request_token(request))
        user_id = to_optional_int(payload.get("user_id")) if payload else None
        response = JSONResponse(
            {
                "authenticated": False,
                "user": None,
                "role": "Guest",
                "permissions": [],
                "organization_id": None,
                "access_level": None,
            }
        )
        clear_auth_cookie(response)
        set_session_cookie(response, generate_session_key())
        observability_service.record_auth_event(
            event_type="auth.session.clear",
            subject_user_id=user_id,
            success=True,
            metadata={
                "client_ip": resolve_client_ip(
                    request.headers, getattr(request, "client", None)
                )
            },
        )
        return response


def register_ws_route(
    app: FastAPI,
    *,
    app_ctx: Callable[[], Any],
    is_local_websocket: Callable[[WebSocket], bool],
    is_secure_websocket: Callable[[WebSocket], bool],
    decode_token_if_present: Callable[[str | None], dict | None],
    resolve_websocket_token: Callable[[WebSocket], str | None],
    session_cookie_name: Callable[[], str],
    resolve_client_ip: Callable[[Any, Any], str | None],
) -> None:
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        _app_ctx = app_ctx()
        network = _app_ctx.network
        from democrai.core.infrastructure.network.providers.bus.ws import WsBusProvider

        # Manage WS connections in dev mode to be open
        if not _app_ctx.dev:
            if not is_local_websocket(ws) and not is_secure_websocket(ws):
                await ws.close(code=1008, reason="secure websocket required")
                return

        websocket_token = resolve_websocket_token(ws)
        payload = decode_token_if_present(websocket_token)
        session_key = (
            getattr(ws, "cookies", {}).get(session_cookie_name())
            or generate_session_key()
        )

        ws_bus = None
        if network:
            for bus in network.buses:
                if isinstance(bus, WsBusProvider):
                    ws_bus = bus
                    break

        if ws_bus:
            from uuid import uuid4

            client_id = f"ws_{uuid4().hex[:8]}"
            if hasattr(network, "register_client_session_key"):
                network.register_client_session_key(ws_bus, client_id, session_key)
            if hasattr(network, "register_client_ip"):
                network.register_client_ip(
                    ws_bus,
                    client_id,
                    resolve_client_ip(ws.headers, getattr(ws, "client", None)),
                )
            if payload and to_optional_int(payload.get("user_id")) is not None:
                network.register_authenticated_client(
                    ws_bus,
                    client_id,
                    user=to_optional_int(payload.get("user_id")),
                    role=payload.get("role"),
                    organization_id=to_optional_int(payload.get("organization_id")),
                    access_level=to_optional_int(payload.get("access_level")),
                )
            preferred_codec = ws.query_params.get("codec")
            initial_messages = (
                [{"jwt": websocket_token}]
                if payload
                and websocket_token
                and to_optional_int(payload.get("user_id")) is not None
                else None
            )
            try:
                await ws_bus.handle_connection(
                    ws,
                    client_id,
                    preferred_codec,
                    initial_messages=initial_messages,
                )
            finally:
                await network._cleanup_client(ws_bus, client_id)
        else:
            await ws.accept()
            await ws.send_json(
                {"type": "error", "error": "WebSocket bus not available"}
            )
            await ws.close()
