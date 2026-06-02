from __future__ import annotations

from democrai.core.application.ai.output_parsers.base import ModelOutputParser
from democrai.core.application.ai.output_parsers.gemma4 import Gemma4OutputParser
from democrai.core.application.ai.output_parsers.generic import GenericOutputParser
from democrai.core.application.ai.output_parsers.gpt_oss import GptOssOutputParser
from democrai.core.application.ai.output_parsers.hermes import HermesOutputParser
from democrai.core.application.ai.output_parsers.llama31 import Llama31OutputParser
from democrai.core.application.ai.output_parsers.qwen3 import Qwen3OutputParser
from democrai.core.application.ai.output_parsers.vllm_gemma import VllmGemmaOutputParser
from democrai.core.application.ai.output_parsers.vllm_qwen import VllmQwenOutputParser


_PARSERS: dict[str, type[ModelOutputParser]] = {
    "gemma4": Gemma4OutputParser,
    "generic": GenericOutputParser,
    "gpt_oss": GptOssOutputParser,
    "hermes": HermesOutputParser,
    "llama31": Llama31OutputParser,
    "qwen3": Qwen3OutputParser,
    "vllm_gemma": VllmGemmaOutputParser,
    "vllm_qwen": VllmQwenOutputParser,
}


def list_output_parsers() -> list[str]:
    return list(_PARSERS.keys())


def get_output_parser(name: str | None = None) -> ModelOutputParser:
    parser_name = str(name or "generic").strip().lower() or "generic"
    parser_cls = _PARSERS.get(parser_name)
    if parser_cls is None:
        raise ValueError(f"unsupported_output_parser:{parser_name}")
    return parser_cls()
