import asyncio
import importlib
import importlib.metadata
from typing import Any, AsyncGenerator, cast

from democrai.sdk.engines import BaseEngine, BaseTTSProvider
from democrai.sdk.dependencies import ensure_import, install_python_packages


_OPENAI_PACKAGE = "openai==2.40.0"
_OPENAI_VERSION = "2.40.0"


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
        install_python_packages([_OPENAI_PACKAGE], modules=["openai"], force=force)

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_module_labels(),
            ok_message="OpenAI TTS engine ready",
            error_message="OpenAI TTS engine requires shared state or local dependencies",
        )

    @classmethod
    def _missing_module_labels(cls) -> list[str]:
        missing = cls._missing_modules(("openai", _OPENAI_PACKAGE))
        if not _openai_version_matches():
            missing.append(_OPENAI_PACKAGE)
        if not _openai_tts_runtime_symbols_available():
            missing.append("OpenAI TTS runtime")
        return missing

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


def _openai_version_matches() -> bool:
    try:
        return importlib.metadata.version("openai").split("+", 1)[0] == _OPENAI_VERSION
    except importlib.metadata.PackageNotFoundError:
        return False


def _openai_tts_runtime_symbols_available() -> bool:
    try:
        openai_mod = importlib.import_module("openai")
    except Exception:
        return False
    AsyncOpenAI = getattr(openai_mod, "AsyncOpenAI", None)
    if not callable(AsyncOpenAI):
        return False
    try:
        client = AsyncOpenAI(api_key="sk-dummy")
    except Exception:
        return False
    return hasattr(getattr(client, "audio", None), "speech")
