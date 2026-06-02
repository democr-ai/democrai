import asyncio
from typing import Any, AsyncGenerator, cast

from democrai.sdk.engines import BaseEngine, BaseTTSProvider
from democrai.sdk.dependencies import ensure_import, install_dependency


class OpenAITTSEngine(BaseEngine, BaseTTSProvider):
    engine_id = "openai_tts"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        install_dependency("openai", force=force)

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_modules(("openai", "openai")),
            ok_message="OpenAI TTS engine ready",
            error_message="OpenAI TTS engine requires shared state or local dependencies",
        )

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)

        openai_mod = ensure_import("openai")
        self.client = openai_mod.AsyncOpenAI(
            api_key=config.get("api_key"),
            base_url=config.get("base_url") or None,
        )

    async def synthesize(self, text: str, options: Any):
        resp = await self.client.audio.speech.create(
            model=options.model or self.model_name or "tts-1",
            voice=options.voice,
            input=text,
            speed=options.speed,
            response_format=options.response_format,
        )
        data = resp.content
        return {
            "data": data,
            "content_type": f"audio/{options.response_format}",
            "usage": {
                "input_characters": len(text),
                "audio_bytes": len(data),
            },
            "usage_metadata": {
                "usage_source": "local",
                "usage_calculation": "engines.openai_tts.engine.OpenAITTSEngine.synthesize",
            },
        }

    async def synthesize_stream(
        self, text: str, options: Any
    ) -> AsyncGenerator[bytes, None]:
        resp = await self.client.audio.speech.create(
            model=options.model or self.model_name or "tts-1",
            voice=options.voice,
            input=text,
            speed=options.speed,
            response_format=options.response_format,
        )
        async for chunk in cast(Any, resp).iter_bytes():
            yield chunk
            await asyncio.sleep(0)
