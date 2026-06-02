from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from democrai.core.application.auth.jwt import session_cookie_name
from democrai.core.application.handler.request import Core
from democrai.core.application.observability.service import observability_service
from democrai.core.infrastructure.network.http.auth import (
    auth_payload_to_response,
    decode_token_claims_unverified,
    decode_token_if_present,
    resolve_client_ip,
    resolve_request_token,
    resolve_websocket_token,
)
from democrai.core.infrastructure.network.http.cookies import (
    clear_auth_cookie,
    set_auth_cookie,
    set_session_cookie,
)
from democrai.core.infrastructure.network.http.routes import (
    register_auth_session_routes,
    register_ws_route,
)
from democrai.core.infrastructure.network.http.websocket import (
    is_local_websocket,
    is_secure_websocket,
)
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.app import (
    RequestContext,
    app_ctx,
    reset_req_ctx,
    set_req_ctx,
)


def _get_http_config_value(key: str, default: Any = None) -> Any:
    ctx = app_ctx()
    config = getattr(ctx, "config", None)
    if ctx and config:
        return config.get(key, default)
    return default


def _http_config_list(key: str, default: list[str]) -> list[str]:
    value = _get_http_config_value(key, default)
    if value is None:
        return list(default)
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _apply_cors_middleware(app: FastAPI) -> None:
    if not (
        normalize_bool(_get_http_config_value("http.cors.enabled", False))
        or bool(getattr(app_ctx(), "setup_mode", False))
    ):
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_http_config_list(
            "http.cors.allow_origins", ["http://localhost:5173"]
        ),
        allow_credentials=normalize_bool(
            _get_http_config_value("http.cors.allow_credentials", True),
            default=True,
        ),
        allow_methods=_http_config_list("http.cors.allow_methods", ["*"]),
        allow_headers=_http_config_list("http.cors.allow_headers", ["*"]),
    )


def _build_http_request_context(request: Request) -> RequestContext:
    payload = decode_token_if_present(resolve_request_token(request))
    return RequestContext(
        app=app_ctx(),
        request_id=request.headers.get("X-Request-Id") or str(uuid4()),
        user=to_optional_int(payload.get("user_id")) if payload else None,
        role=payload.get("role") if payload else None,
        organization_id=to_optional_int(payload.get("organization_id"))
        if payload
        else None,
        access_level=to_optional_int(payload.get("access_level")) if payload else None,
        channel="http",
        session_key=getattr(request, "cookies", {}).get(session_cookie_name()),
        client_ip=resolve_client_ip(request.headers, getattr(request, "client", None)),
        module_name="core",
    )


def _install_http_request_context_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def http_request_context_middleware(request: Request, call_next):
        token_ctx = set_req_ctx(_build_http_request_context(request))
        try:
            return await call_next(request)
        finally:
            reset_req_ctx(token_ctx)


def build_fastapi_app(core: Core, *, app_mode: str = "full") -> FastAPI:
    app = FastAPI()
    _apply_cors_middleware(app)
    _install_http_request_context_middleware(app)

    if app_mode == "media_proxy_only":
        from democrai.core.application.handler.services.media import media_desktop_router

        app.include_router(media_desktop_router, prefix="/media")
        return app

    from democrai.core.application.handler.services.media import media_router

    @app.get("/ping")
    async def ping():
        return await core.handle({"type": "ping"})

    app.include_router(media_router, prefix="/media")

    delete_session_by_key = None
    session_service = getattr(core, "session_service", None)
    if session_service is not None:
        store = getattr(session_service, "store", None)
        if store is not None and callable(getattr(store, "delete", None)):
            delete_session_by_key = store.delete

    register_auth_session_routes(
        app,
        decode_token_if_present=decode_token_if_present,
        decode_token_claims_unverified=decode_token_claims_unverified,
        resolve_request_token=resolve_request_token,
        auth_payload_to_response=auth_payload_to_response,
        set_session_cookie=set_session_cookie,
        clear_auth_cookie=clear_auth_cookie,
        set_auth_cookie=set_auth_cookie,
        resolve_client_ip=resolve_client_ip,
        observability_service=observability_service,
        session_cookie_name=session_cookie_name,
        delete_session_by_key=delete_session_by_key,
    )
    register_ws_route(
        app,
        app_ctx=lambda: app_ctx(),
        is_local_websocket=is_local_websocket,
        is_secure_websocket=is_secure_websocket,
        decode_token_if_present=decode_token_if_present,
        resolve_websocket_token=resolve_websocket_token,
        session_cookie_name=session_cookie_name,
    )

    return app
