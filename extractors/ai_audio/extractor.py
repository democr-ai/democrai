from __future__ import annotations

from typing import Any

from democrai.sdk.extractors import BaseExtractor, ExtractorResult, ExtractorSource
from democrai.sdk.dependencies import ensure_extractor_venv


class AIAudioExtractor(BaseExtractor):
    extractor_id = "ai_audio"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        install_config: dict[str, Any] | None = None,
    ) -> None:
        ensure_extractor_venv()

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._build_ready_payload(
            ok_message="AI audio extractor ready",
            error_message="AI audio extractor is not ready",
        )

    def _extract_source(self, source: ExtractorSource) -> ExtractorResult:
        mime_type = str(source.mime_type or "").strip().lower()
        if not mime_type.startswith("audio/"):
            raise ValueError(f"unsupported_audio_source:{source.name}")
        transcription = self._run_async(self._transcribe_audio(source))
        text = str(transcription.get("text") or "").strip()
        if not text:
            raise RuntimeError("ai_audio_extractor_empty_transcription")
        markdown = f"## Transcript\n\n{text}"
        chunks = self._chunk_text(
            text,
            chunk_size=self._chunk_size(),
            overlap=self._chunk_overlap(),
            source_name=source.name,
        )
        return ExtractorResult(
            source=source,
            structure={
                "type": "audio",
                "name": source.name,
                "source": source.source,
                "mime_type": source.mime_type,
                "size_bytes": len(source.data),
                "language": transcription.get("language"),
                "duration": transcription.get("duration"),
                "segment_count": len(transcription.get("segments") or []),
            },
            markdown_content=markdown,
            chunks=chunks,
            index=self._build_simple_index(
                source.name, chunks=chunks, source=source.source
            ),
        )

    async def _transcribe_audio(self, source: ExtractorSource) -> dict[str, Any]:
        model_registry_id = int(self._config.get("model_registry_id") or 0)
        if model_registry_id <= 0:
            raise RuntimeError("ai_audio_model_registry_id_required")
        result = await self._sdk().ai.get_provider_by_model_registry_id(
            model_registry_id,
        )
        if result.get("status") != "ok" or result.get("provider") is None:
            raise RuntimeError(result.get("error") or "audio_provider_unavailable")
        transcription = await result["provider"].transcribe(
            source.data,
            language=str(self._config.get("language") or "").strip() or None,
        )
        transcription = _response_result(transcription)
        if isinstance(transcription, dict):
            return {
                "text": str(transcription.get("text") or "").strip(),
                "language": str(transcription.get("language") or "").strip() or None,
                "duration": transcription.get("duration"),
                "segments": list(transcription.get("segments") or []),
            }
        return {
            "text": str(getattr(transcription, "text", "") or "").strip(),
            "language": str(getattr(transcription, "language", "") or "").strip()
            or None,
            "duration": getattr(transcription, "duration", None),
            "segments": list(getattr(transcription, "segments", None) or []),
        }

    def _chunk_size(self) -> int:
        return _int_config(self._config, "chunk_size", default=1200)

    def _chunk_overlap(self) -> int:
        return _int_config(self._config, "chunk_overlap", default=150)


def _response_result(response: Any) -> Any:
    if isinstance(response, dict) and "result" in response:
        return response.get("result")
    return getattr(response, "result", response)


def _config_value(config: dict[str, Any], key: str, default: int) -> Any:
    value = config.get(key)
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return value


def _int_config(config: dict[str, Any], key: str, *, default: int) -> int:
    value = _config_value(config, key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_ai_audio_{key}") from exc
