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
        markdown = f"## Transcript\n\n{text}" if text else ""
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
                "empty_transcription": not bool(text),
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
        return _transcription_payload(transcription)

    def _chunk_size(self) -> int:
        return _int_config(self._config, "chunk_size", default=1200)

    def _chunk_overlap(self) -> int:
        return _int_config(self._config, "chunk_overlap", default=150)


def _response_result(response: Any) -> Any:
    if isinstance(response, dict) and "result" in response:
        return response.get("result")
    return getattr(response, "result", response)


def _transcription_payload(response: Any) -> dict[str, Any]:
    transcription, candidates = _best_transcription_value(response)
    if isinstance(transcription, dict):
        return {
            "text": str(transcription.get("text") or "").strip(),
            "language": str(transcription.get("language") or "").strip() or None,
            "duration": transcription.get("duration"),
            "segments": list(transcription.get("segments") or []),
            "_debug": _candidate_debug(candidates),
        }
    return {
        "text": str(getattr(transcription, "text", "") or "").strip(),
        "language": str(getattr(transcription, "language", "") or "").strip()
        or None,
        "duration": getattr(transcription, "duration", None),
        "segments": list(getattr(transcription, "segments", None) or []),
        "_debug": _candidate_debug(candidates),
    }


def _best_transcription_value(response: Any) -> tuple[Any, list[Any]]:
    candidates: list[Any] = []
    queue: list[Any] = [response]
    seen_ids: set[int] = set()
    for _ in range(16):
        if not queue:
            break
        candidate = queue.pop(0)
        candidate_id = id(candidate)
        if candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        candidates.append(candidate)
        next_value = _response_result(candidate)
        if next_value is not candidate:
            queue.append(next_value)
        if isinstance(candidate, dict):
            for key in ("value", "data", "transcription", "payload"):
                nested = candidate.get(key)
                if nested is not None:
                    queue.append(nested)
    for candidate in candidates:
        if _transcription_text(candidate):
            return candidate, candidates
    return (candidates[-1] if candidates else response), candidates


def _transcription_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return str(getattr(value, "text", "") or "").strip()


def _safe_debug_shape(value: Any) -> str:
    if isinstance(value, dict):
        parts = [f"type=dict", f"keys={','.join(sorted(str(key) for key in value.keys()))}"]
        text = value.get("text")
        if text is not None:
            parts.append(f"text_len={len(str(text))}")
        segments = value.get("segments")
        if isinstance(segments, list):
            parts.append(f"segments_len={len(segments)}")
        return ";".join(parts)
    text = getattr(value, "text", None)
    return f"type={type(value).__name__};text_len={len(str(text or ''))}"


def _candidate_debug(candidates: list[Any]) -> str:
    return "|".join(_safe_debug_shape(candidate) for candidate in candidates[:8])


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
