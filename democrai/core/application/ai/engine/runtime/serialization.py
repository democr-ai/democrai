from __future__ import annotations

import base64
from enum import Enum
from typing import Any, Callable

from democrai.core.application.ai.engine.schemas.audio import SpeechResponse
from democrai.core.application.ai.engine.schemas.audio import SpeechUsage
from democrai.core.application.ai.engine.schemas.audio import TranscriptionResponse
from democrai.core.application.ai.engine.schemas.completion import ClassificationResult
from democrai.core.application.ai.engine.schemas.completion import ClassificationOptions
from democrai.core.application.ai.engine.schemas.completion import CompletionOptions
from democrai.core.application.ai.engine.schemas.completion import CompletionResponse
from democrai.core.application.ai.engine.schemas.completion import ContentPart
from democrai.core.application.ai.engine.schemas.completion import Function
from democrai.core.application.ai.engine.schemas.completion import Message
from democrai.core.application.ai.engine.schemas.completion import RerankResult
from democrai.core.application.ai.engine.schemas.completion import RerankOptions
from democrai.core.application.ai.engine.schemas.completion import StreamChunk
from democrai.core.application.ai.engine.schemas.completion import TokenExtractionResult
from democrai.core.application.ai.engine.schemas.completion import Tool
from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.engine.schemas.kg import ExtractedKnowledgeGraph
from democrai.core.application.ai.engine.schemas.kg import KGEntity
from democrai.core.application.ai.engine.schemas.kg import KGExtractionOptions
from democrai.core.application.ai.engine.schemas.kg import KGRelation
from democrai.core.application.ai.engine.schemas.runtime import EngineMethodResponse
from democrai.core.application.ai.engine.schemas.runtime import EngineStreamFinal
from democrai.core.application.ai.engine.schemas.runtime import EngineUsage


_MODEL_TYPES = {
    "ContentPart": ContentPart,
    "Message": Message,
    "CompletionOptions": CompletionOptions,
    "Function": Function,
    "Tool": Tool,
    "ToolCall": ToolCall,
    "CompletionResponse": CompletionResponse,
    "ClassificationResult": ClassificationResult,
    "ClassificationOptions": ClassificationOptions,
    "RerankResult": RerankResult,
    "RerankOptions": RerankOptions,
    "StreamChunk": StreamChunk,
    "TokenExtractionResult": TokenExtractionResult,
    "SpeechResponse": SpeechResponse,
    "SpeechUsage": SpeechUsage,
    "TranscriptionResponse": TranscriptionResponse,
    "KGEntity": KGEntity,
    "KGRelation": KGRelation,
    "KGExtractionOptions": KGExtractionOptions,
    "ExtractedKnowledgeGraph": ExtractedKnowledgeGraph,
    "EngineMethodResponse": EngineMethodResponse,
    "EngineStreamFinal": EngineStreamFinal,
    "EngineUsage": EngineUsage,
}


BinaryPacker = Callable[[bytes | bytearray], Any]


def json_value(value: Any, *, binary_packer: BinaryPacker | None = None) -> Any:
    if isinstance(value, EngineMethodResponse):
        return {
            "__model__": "EngineMethodResponse",
            "value": {
                "result": json_value(value.result, binary_packer=binary_packer),
                "usage": json_value(value.usage, binary_packer=binary_packer),
                "duration_ms": value.duration_ms,
                "tokens_per_second": value.tokens_per_second,
                "metadata": json_value(value.metadata, binary_packer=binary_packer),
            },
        }
    if isinstance(value, EngineStreamFinal):
        return {
            "__model__": "EngineStreamFinal",
            "value": {
                "usage": json_value(value.usage, binary_packer=binary_packer),
                "duration_ms": value.duration_ms,
                "tokens_per_second": value.tokens_per_second,
                "metadata": json_value(value.metadata, binary_packer=binary_packer),
            },
        }
    if isinstance(value, EngineUsage):
        return {
            "__model__": "EngineUsage",
            "value": value.to_dict(),
        }
    if hasattr(value, "model_dump"):
        return {
            "__model__": value.__class__.__name__,
            "value": json_value(
                value.model_dump(mode="python"),
                binary_packer=binary_packer,
            ),
        }
    if isinstance(value, bytes):
        if binary_packer is not None:
            return binary_packer(value)
        return {
            "__bytes__": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, bytearray):
        if binary_packer is not None:
            return binary_packer(value)
        return {
            "__bytes__": base64.b64encode(bytes(value)).decode("ascii"),
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {
            str(key): json_value(current, binary_packer=binary_packer)
            for key, current in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [json_value(item, binary_packer=binary_packer) for item in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def python_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "__bytes__" in value:
            return base64.b64decode(value["__bytes__"])
        if "__model__" in value and "value" in value:
            model_name = value["__model__"]
            model_type = _MODEL_TYPES.get(model_name)
            payload = python_value(value["value"])
            if model_name == "EngineUsage" and isinstance(payload, dict):
                return EngineUsage(**payload)
            if model_name == "EngineMethodResponse" and isinstance(payload, dict):
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    usage = EngineUsage(**usage)
                return EngineMethodResponse(
                    result=payload.get("result"),
                    usage=usage if isinstance(usage, EngineUsage) else EngineUsage(),
                    duration_ms=payload["duration_ms"],
                    tokens_per_second=payload["tokens_per_second"],
                    metadata=payload["metadata"],
                )
            if model_name == "EngineStreamFinal" and isinstance(payload, dict):
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    usage = EngineUsage(**usage)
                return EngineStreamFinal(
                    usage=usage if isinstance(usage, EngineUsage) else EngineUsage(),
                    duration_ms=payload["duration_ms"],
                    tokens_per_second=payload["tokens_per_second"],
                    metadata=payload["metadata"],
                )
            if model_type is not None and isinstance(payload, dict):
                return model_type(**payload)
            return payload
        return {key: python_value(current) for key, current in value.items()}
    if isinstance(value, list):
        return [python_value(item) for item in value]
    return value
