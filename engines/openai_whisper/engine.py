import io
import importlib
import importlib.metadata
import mimetypes
from typing import Any, Optional

from democrai.sdk.engines import BaseEngine, BaseSTTProvider
from democrai.sdk.dependencies import ensure_import, install_python_packages


_OPENAI_PACKAGE = "openai==2.40.0"
_OPENAI_VERSION = "2.40.0"


def _disable_system_mime_type_lookup() -> None:
    mimetypes.knownfiles = []
    mimetypes.init(files=[])


def _audio_upload_name(audio_data: bytes) -> str:
    header = bytes(audio_data[:32])
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "audio.wav"
    if header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "audio.mp3"
    if header.startswith(b"OggS"):
        return "audio.ogg"
    if header.startswith(b"fLaC"):
        return "audio.flac"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio.webm"
    if b"ftyp" in header[:16]:
        return "audio.m4a"
    return "audio.wav"


class OpenAIWhisperEngine(BaseEngine, BaseSTTProvider):
    engine_id = "openai_whisper"

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
            ok_message="OpenAI Whisper engine ready",
            error_message="OpenAI Whisper engine requires shared state or local dependencies",
        )

    @classmethod
    def _missing_module_labels(cls) -> list[str]:
        missing = cls._missing_modules(("openai", _OPENAI_PACKAGE))
        if not _openai_version_matches():
            missing.append(_OPENAI_PACKAGE)
        if not _openai_stt_runtime_symbols_available():
            missing.append("OpenAI Whisper runtime")
        return missing

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)
        _disable_system_mime_type_lookup()

        openai_mod = ensure_import("openai", dependency_key="openai")
        self.client = openai_mod.AsyncOpenAI(
            api_key=config.get("api_key"),
            base_url=config.get("base_url") or "https://api.openai.com/v1",
        )

    async def transcribe(
        self, audio_data: bytes, language: Optional[str] = None
    ):
        _disable_system_mime_type_lookup()
        audio_file = io.BytesIO(audio_data)
        audio_file.name = _audio_upload_name(audio_data)
        kwargs: dict = {"file": audio_file, "model": self.model_name or "whisper-1"}
        if language:
            kwargs["language"] = language
        resp = await self.client.audio.transcriptions.create(**kwargs)
        result = {"text": resp.text}
        usage = _openai_usage_dict(resp)
        if usage is not None:
            result["usage"] = usage
            result["usage_metadata"] = {"usage_source": "provider"}
        return result


def _openai_usage_dict(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt_tokens = _usage_value(usage, "prompt_tokens")
    if prompt_tokens is None:
        prompt_tokens = _usage_value(usage, "input_tokens")
    completion_tokens = _usage_value(usage, "completion_tokens")
    if completion_tokens is None:
        completion_tokens = _usage_value(usage, "output_tokens")
    total_tokens = _usage_value(usage, "total_tokens")
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        return None
    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }


def _usage_value(usage: Any, key: str) -> int | None:
    raw = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
    try:
        return int(raw)
    except Exception:
        return None


def _openai_version_matches() -> bool:
    try:
        return importlib.metadata.version("openai").split("+", 1)[0] == _OPENAI_VERSION
    except importlib.metadata.PackageNotFoundError:
        return False


def _openai_stt_runtime_symbols_available() -> bool:
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
    return hasattr(getattr(client, "audio", None), "transcriptions")
