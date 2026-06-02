from __future__ import annotations

from fastapi.responses import JSONResponse

from democrai.core.application.auth.jwt import (
    auth_cookie_domain,
    auth_cookie_http_only,
    auth_cookie_name,
    auth_cookie_samesite,
    auth_cookie_secure,
    session_cookie_name,
)


def set_auth_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key=auth_cookie_name(),
        value=token,
        httponly=auth_cookie_http_only(),
        secure=auth_cookie_secure(),
        samesite=auth_cookie_samesite(),
        domain=auth_cookie_domain(),
        path="/",
    )


def clear_auth_cookie(response: JSONResponse) -> None:
    response.delete_cookie(
        key=auth_cookie_name(),
        domain=auth_cookie_domain(),
        path="/",
        secure=auth_cookie_secure(),
        samesite=auth_cookie_samesite(),
    )


def set_session_cookie(response: JSONResponse, session_key: str) -> None:
    response.set_cookie(
        key=session_cookie_name(),
        value=session_key,
        httponly=auth_cookie_http_only(),
        secure=auth_cookie_secure(),
        samesite=auth_cookie_samesite(),
        domain=auth_cookie_domain(),
        path="/",
    )
