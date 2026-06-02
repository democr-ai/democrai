from __future__ import annotations
import asyncio
import os
from typing import Any, Dict, Optional, Callable
from fastapi import WebSocket, WebSocketDisconnect
from democrai.core.infrastructure.network.contracts import BusProvider
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.infrastructure.network.codec.ws import (
    normalize_codec,
    encode_message,
    decode_message,
    WsCodec,
    runtime_diagnostics,
)
from democrai.core.runtime.observability.profiling import current_request_profiler
import time


class WsBusProvider(BusProvider):
    """
    WebSocket implementation of BusProvider.
    Acts as a bridge between FastAPI's WebSocket endpoints and the Network coordinator.
    """

    def __init__(self) -> None:
        self.on_message: Optional[Callable[[Any, Dict[str, Any]], None]] = None
        self.on_disconnect: Optional[Callable[[Any], None]] = None
        self._sockets: Dict[Any, WebSocket] = {}
        self._loops: Dict[Any, asyncio.AbstractEventLoop] = {}
        self._codecs: Dict[Any, WsCodec] = {}

    def start(self) -> None:
        app_ctx().logger.info(
            "[WsBus] Provider ready (waiting for connections via FastAPI)"
        )
        if os.getenv("DEMOCRAI_DEBUG_WS_RUNTIME") == "1":
            codec = normalize_codec(
                app_ctx().config.get("network.ws.codec", "json")
                if app_ctx().config
                else "json"
            )
            allow_override = (
                bool(
                    app_ctx().config.get("network.ws.allow_client_codec_override", True)
                )
                if app_ctx().config
                else True
            )
            diag = runtime_diagnostics()
            app_ctx().logger.info(
                f"[WsRuntimeDebug] codec={codec} allow_override={allow_override} "
                f"json_encoder_module={diag['json_encoder_module']} "
                f"json_decoder_module={diag['json_decoder_module']} "
                f"_json_loaded={diag['_json_loaded']} "
                f"json_module_file={diag['json_module_file']} "
                f"zlib_module_file={diag['zlib_module_file']}"
            )

    def stop(self) -> None:
        # Closing all sockets
        # Note: In a real environment, we'd want to close them gracefully
        self._sockets.clear()
        self._loops.clear()
        self._codecs.clear()

    def send(self, client_id: Any, message: Dict[str, Any]) -> None:
        ws = self._sockets.get(client_id)
        loop = self._loops.get(client_id)
        if ws and loop:
            try:
                profiler = current_request_profiler()
                codec = self._codecs.get(client_id) or normalize_codec(
                    app_ctx().config.get("network.ws.codec", "json")
                    if app_ctx().config
                    else "json"
                )
                encode_started = time.perf_counter()
                frame_kind, payload = encode_message(message, codec)
                if profiler is not None:
                    profiler.add_ms(
                        "transport.ws.encode",
                        (time.perf_counter() - encode_started) * 1000.0,
                    )
                if frame_kind == "bytes":
                    schedule_started = time.perf_counter()
                    asyncio.run_coroutine_threadsafe(ws.send_bytes(payload), loop)
                else:
                    schedule_started = time.perf_counter()
                    asyncio.run_coroutine_threadsafe(ws.send_text(payload), loop)
                if profiler is not None:
                    profiler.add_ms(
                        "transport.ws.enqueue",
                        (time.perf_counter() - schedule_started) * 1000.0,
                    )
            except Exception as e:
                app_ctx().logger.error(f"[WsBus] Error sending to {client_id}: {e}")

    def broadcast(self, message: Dict[str, Any]) -> None:
        for client_id, ws in self._sockets.items():
            loop = self._loops.get(client_id)
            if loop:
                try:
                    codec = self._codecs.get(client_id) or normalize_codec(
                        app_ctx().config.get("network.ws.codec", "json")
                        if app_ctx().config
                        else "json"
                    )
                    frame_kind, payload = encode_message(message, codec)
                    if frame_kind == "bytes":
                        asyncio.run_coroutine_threadsafe(ws.send_bytes(payload), loop)
                    else:
                        asyncio.run_coroutine_threadsafe(ws.send_text(payload), loop)
                except Exception:
                    pass

    async def handle_connection(
        self,
        websocket: WebSocket,
        client_id: Any,
        preferred_codec: str | None = None,
        initial_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        """Entry point for FastAPI to pass a new websocket connection."""
        await websocket.accept()
        self._sockets[client_id] = websocket
        self._loops[client_id] = asyncio.get_running_loop()  # Capture the Uvicorn loop
        configured_codec = normalize_codec(
            app_ctx().config.get("network.ws.codec", "json")
            if app_ctx().config
            else "json"
        )
        allow_override = (
            bool(app_ctx().config.get("network.ws.allow_client_codec_override", True))
            if app_ctx().config
            else True
        )
        resolved_codec = configured_codec
        if allow_override and preferred_codec:
            resolved_codec = normalize_codec(preferred_codec, configured_codec)
        self._codecs[client_id] = resolved_codec
        app_ctx().logger.info(f"[WsBus] Client {client_id} connected via WebSocket")

        for message in list(initial_messages or []):
            frame_kind, payload = encode_message(message, resolved_codec)
            if frame_kind == "bytes":
                await websocket.send_bytes(payload)
            else:
                await websocket.send_text(payload)

        # Trigger initial render/init for the web client
        if self.on_message:
            self.on_message(client_id, {"type": "init"})

        try:
            while True:
                packet = await websocket.receive()
                text = packet.get("text")
                data = packet.get("bytes")
                if packet.get("type") == "websocket.disconnect":
                    break
                decode_started = time.perf_counter()
                decoded = decode_message(
                    text=text,
                    data=data,
                    codec=self._codecs.get(client_id, configured_codec),
                )
                decoded["_ws_decode_ms"] = (
                    time.perf_counter() - decode_started
                ) * 1000.0
                decoded["_ws_handoff_started_at"] = time.perf_counter()
                if self.on_message:
                    # In WsBus, we are already in an async context (FastAPI),
                    # but the Network coordinator expects to be called
                    # from either thread.
                    self.on_message(client_id, decoded)
        except WebSocketDisconnect:
            app_ctx().logger.info(f"[WsBus] Client {client_id} disconnected")
        except Exception as e:
            app_ctx().logger.error(f"[WsBus] Error on client {client_id}: {e}")
        finally:
            self._sockets.pop(client_id, None)
            self._loops.pop(client_id, None)
            self._codecs.pop(client_id, None)
            if self.on_disconnect:
                self.on_disconnect(client_id)
