from typing import Any, AsyncGenerator

from democrai.sdk.engines import BaseEngine, BaseTTSProvider
from democrai.sdk.dependencies import ensure_import, install_dependency


class EdgeEngine(BaseEngine, BaseTTSProvider):
    engine_id = "edge"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        install_dependency("edge-tts", force=force)

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_modules(("edge_tts", "edge-tts")),
            ok_message="Edge TTS engine ready",
            error_message="Edge TTS engine requires shared state or local dependencies",
        )

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)
        self.default_voice = config.get("voice") or self.model_name or "en-US-AndrewNeural"
        self.default_rate = config.get("rate") or "+0%"

    async def synthesize(self, text: str, options: Any):
        edge_tts = ensure_import("edge_tts", dependency_key="edge_tts")
        communicate = edge_tts.Communicate(
            text,
            options.voice or self.default_voice,
            rate=self.default_rate,
        )
        data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        return {"data": data, "content_type": "audio/mpeg"}

    async def synthesize_stream(
        self, text: str, options: Any
    ) -> AsyncGenerator[bytes, None]:
        edge_tts = ensure_import("edge_tts", dependency_key="edge_tts")
        communicate = edge_tts.Communicate(
            text,
            options.voice or self.default_voice,
            rate=self.default_rate,
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
