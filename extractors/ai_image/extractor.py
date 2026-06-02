from __future__ import annotations

import os
from typing import Any

from democrai.sdk.extractors import BaseExtractor, ExtractorResult, ExtractorSource


class AIImageExtractor(BaseExtractor):
    extractor_id = "ai_image"

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._build_ready_payload(
            ok_message="AI image extractor ready",
            error_message="AI image extractor is not ready",
        )

    def _extract_source(self, source: ExtractorSource) -> ExtractorResult:
        mime_type = str(source.mime_type or "").strip().lower()
        if not mime_type.startswith("image/"):
            raise ValueError(f"unsupported_image_source:{source.name}")
        markdown = self._run_async(self._describe_image(source))
        chunks = self._chunk_text(
            markdown,
            chunk_size=self._chunk_size(),
            overlap=self._chunk_overlap(),
            source_name=source.name,
        )
        return ExtractorResult(
            source=source,
            structure={
                "type": "image",
                "name": source.name,
                "source": source.source,
                "mime_type": source.mime_type,
                "size_bytes": len(source.data),
            },
            markdown_content=markdown,
            chunks=chunks,
            index=self._build_simple_index(
                source.name, chunks=chunks, source=source.source
            ),
            images=[
                {
                    "id": f"{source.source}:image:0",
                    "name": source.name,
                    "source": source.source,
                    "mime_type": source.mime_type,
                    "size_bytes": len(source.data),
                }
            ],
        )

    async def _describe_image(self, source: ExtractorSource) -> str:
        from democrai.sdk.engines import (
            CompletionOptions,
            ContentPart,
            ContentType,
            Message,
            MessageRole,
        )

        model_registry_id = int(self._config.get("model_registry_id") or 0)
        if model_registry_id <= 0:
            raise RuntimeError("ai_image_model_registry_id_required")
        result = await self._sdk().ai.get_provider_by_model_registry_id(
            model_registry_id,
        )
        if result.get("status") != "ok" or result.get("provider") is None:
            raise RuntimeError(result.get("error") or "ai_image_provider_unavailable")
        response = await result["provider"].generate_completion(
            messages=[
                Message(
                    role=MessageRole.USER,
                    content=[
                        ContentPart(type=ContentType.TEXT, text=self._prompt()),
                        ContentPart(
                            type=ContentType.IMAGE,
                            data=source.data,
                            mime_type=source.mime_type or "image/png",
                        ),
                    ],
                )
            ],
            options=CompletionOptions(
                temperature=self._temperature(),
                top_p=self._top_p(),
                max_tokens=self._max_tokens(),
                stream=False,
            ),
        )
        content = str(getattr(response, "content", "") or "").strip()
        if not content:
            raise RuntimeError("ai_image_extractor_empty_response")
        return content

    def _prompt(self) -> str:
        return str(
            self._config.get("prompt")
            or os.getenv(
                "DEMOCRAI_EXTRACTOR_AI_IMAGE_PROMPT",
                "Read this image and return a markdown description with visible text, layout, entities, and notable details.",
            )
        ).strip()

    def _temperature(self) -> float:
        return _float_config(self._config, "temperature", default=0.0)

    def _top_p(self) -> float:
        return _float_config(self._config, "top_p", default=1.0)

    def _max_tokens(self) -> int:
        return _int_config(self._config, "max_tokens", default=900)

    def _chunk_size(self) -> int:
        return _int_config(self._config, "chunk_size", default=1200)

    def _chunk_overlap(self) -> int:
        return _int_config(self._config, "chunk_overlap", default=150)


def _config_value(config: dict[str, Any], key: str, default: int | float) -> Any:
    value = config.get(key)
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return value


def _float_config(config: dict[str, Any], key: str, *, default: float) -> float:
    value = _config_value(config, key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_ai_image_{key}") from exc


def _int_config(config: dict[str, Any], key: str, *, default: int) -> int:
    value = _config_value(config, key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_ai_image_{key}") from exc
