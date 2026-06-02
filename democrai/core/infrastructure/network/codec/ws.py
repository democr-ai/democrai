from __future__ import annotations

import json
import os
import sys
import zlib
from typing import Any, Dict, Literal, Tuple

WsCodec = Literal["json", "deflate-json"]
FrameKind = Literal["text", "bytes"]

SUPPORTED_CODECS = {"json", "deflate-json"}


def runtime_diagnostics() -> Dict[str, Any]:
    encoder = getattr(json.encoder, "c_make_encoder", None)
    decoder = getattr(json.decoder, "scanstring", None)
    return {
        "json_encoder_module": getattr(encoder, "__module__", None),
        "json_decoder_module": getattr(decoder, "__module__", None),
        "json_module_file": getattr(json, "__file__", None),
        "_json_loaded": "_json" in sys.modules,
        "zlib_module_file": getattr(zlib, "__file__", None),
        "ws_codec_env": os.getenv("DEMOCRAI_DEBUG_WS_RUNTIME"),
    }


def normalize_codec(value: Any, default: WsCodec = "json") -> WsCodec:
    raw = str(value or "").strip().lower()
    if raw in SUPPORTED_CODECS:
        return raw  # type: ignore[return-value]
    return default


def encode_message(message: Dict[str, Any], codec: WsCodec) -> Tuple[FrameKind, Any]:
    serialized = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    if codec == "deflate-json":
        return "bytes", zlib.compress(serialized, level=6)
    return "text", serialized.decode("utf-8")


def decode_message(
    *,
    text: str | None,
    data: bytes | None,
    codec: WsCodec,
) -> Dict[str, Any]:
    if text is not None:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("WebSocket text payload must decode to an object")
        return parsed

    if data is None:
        raise ValueError("Empty WebSocket payload")

    payload = data
    if codec == "deflate-json":
        _MAX_DECOMPRESSED = 16 * 1024 * 1024  # 16 MB
        dec = zlib.decompressobj()
        payload = dec.decompress(data, _MAX_DECOMPRESSED)
        if dec.unconsumed_tail:
            raise ValueError("WebSocket payload exceeds decompressed size limit")

    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("WebSocket binary payload must decode to an object")
    return parsed
