from __future__ import annotations

from fastapi import WebSocket


def is_local_websocket(ws: WebSocket) -> bool:
    host = (ws.url.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def is_secure_websocket(ws: WebSocket) -> bool:
    forwarded_proto = (ws.headers.get("x-forwarded-proto") or "").strip().lower()
    if forwarded_proto in {"https", "wss"}:
        return True
    return (ws.url.scheme or "").strip().lower() == "wss"
