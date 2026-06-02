from __future__ import annotations

import json
import re

from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.output_parsers.base import ModelOutputParser
from democrai.core.application.ai.output_parsers.hermes import _parse_hermes_parameters
from democrai.core.application.ai.output_parsers.qwen3 import _pending_reasoning_marker_start
from democrai.core.application.ai.output_parsers.qwen3 import _pending_think_start
from democrai.core.application.ai.output_parsers.qwen3 import _qwen3_reasoning_content
from democrai.core.application.ai.output_parsers.types import ParsedModelOutput
from democrai.core.application.ai.output_parsers.types import StreamParseState


_TOOL_CALL_START = "<tool_call>"
_TOOL_CALL_END = "</tool_call>"
_FUNCTION_START = "<function="
_FUNCTION_END = "</function>"


class VllmQwenOutputParser(ModelOutputParser):
    def parse(self, text: str) -> ParsedModelOutput:
        reasoning, content = _qwen3_reasoning_content(text)
        parsed = _parse_vllm_qwen_tool_calls(content or "")
        return ParsedModelOutput(
            content=parsed.content,
            reasoning=reasoning,
            tool_calls=parsed.tool_calls,
        )

    def feed(self, state: StreamParseState, text: str) -> list[ParsedModelOutput]:
        if not text:
            return []
        state.buffer += text
        return _stream_deltas(state)

    def finish(self, state: StreamParseState) -> list[ParsedModelOutput]:
        outputs = _stream_deltas(state)
        state.buffer = ""
        return outputs


def _stream_deltas(state: StreamParseState) -> list[ParsedModelOutput]:
    raw = str(state.buffer or "")
    if not raw.strip():
        return []
    if _pending_think_start(raw) or _pending_reasoning_marker_start(raw):
        return []
    reasoning, content = _qwen3_reasoning_content(raw)
    if content and _should_buffer_vllm_qwen_tool_fragment(content):
        return []
    parsed = _parse_vllm_qwen_tool_calls(content or "")
    emitted_reasoning_len = int(getattr(state, "emitted_reasoning_len", 0) or 0)
    emitted_content_len = int(getattr(state, "emitted_content_len", 0) or 0)
    emitted_tool_call_count = int(getattr(state, "emitted_tool_call_count", 0) or 0)
    reasoning_delta = (
        reasoning[emitted_reasoning_len:]
        if reasoning and len(reasoning) > emitted_reasoning_len
        else None
    )
    content_delta = (
        parsed.content[emitted_content_len:]
        if parsed.content and len(parsed.content) > emitted_content_len
        else None
    )
    tool_call_delta = parsed.tool_calls[emitted_tool_call_count:]
    if reasoning:
        state.emitted_reasoning_len = len(reasoning)
    if parsed.content:
        state.emitted_content_len = len(parsed.content)
    if parsed.tool_calls:
        state.emitted_tool_call_count = len(parsed.tool_calls)
    if not reasoning_delta and not content_delta and not tool_call_delta:
        return []
    return [
        ParsedModelOutput(
            content=content_delta,
            reasoning=reasoning_delta,
            tool_calls=tool_call_delta,
        )
    ]


def _parse_vllm_qwen_tool_calls(text: str) -> ParsedModelOutput:
    raw = str(text or "")
    tool_calls: list[ToolCall] = []
    content = raw
    matches = list(
        re.finditer(
            rf"{re.escape(_TOOL_CALL_START)}.*?{re.escape(_TOOL_CALL_END)}|{re.escape(_FUNCTION_START)}[^>]*>.*?{re.escape(_FUNCTION_END)}",
            raw,
            flags=re.DOTALL,
        )
    )
    for index, match in enumerate(matches):
        name, arguments = _parse_vllm_qwen_tool_payload(match.group(0))
        tool_calls.append(
            ToolCall(
                id=f"tool_call_{index}",
                type="function",
                function_name=name,
                arguments=json.dumps(arguments, ensure_ascii=False),
            )
        )
    if not tool_calls:
        return ParsedModelOutput(content=raw or None)
    for match in reversed(matches):
        content = content[: match.start()] + content[match.end() :]
    return ParsedModelOutput(content=content.strip() or None, tool_calls=tool_calls)


def _parse_vllm_qwen_tool_payload(text: str) -> tuple[str, dict[str, object]]:
    raw = str(text or "").strip()
    if raw.startswith(_TOOL_CALL_START):
        raw = raw[len(_TOOL_CALL_START) :]
        if raw.endswith(_TOOL_CALL_END):
            raw = raw[: -len(_TOOL_CALL_END)]
        raw = raw.strip()
    function_match = re.search(r"<function=([^>]+)>", raw)
    if function_match is None:
        raise ValueError("vllm_qwen_tool_call_invalid")
    name = function_match.group(1).strip()
    body = raw[function_match.end() :]
    end_index = body.find(_FUNCTION_END)
    if end_index >= 0:
        body = body[:end_index]
    return name, _parse_hermes_parameters(body)


def _should_buffer_vllm_qwen_tool_fragment(text: str) -> bool:
    raw = str(text or "").lstrip()
    if not raw:
        return False
    if _TOOL_CALL_START.startswith(raw) or _FUNCTION_START.startswith(raw):
        return True
    if raw.startswith(_TOOL_CALL_START):
        return _TOOL_CALL_END not in raw
    if raw.startswith(_FUNCTION_START):
        return _FUNCTION_END not in raw
    last_tool = raw.rfind("<")
    if last_tool < 0:
        return False
    suffix = raw[last_tool:]
    return any(marker.startswith(suffix) for marker in (_TOOL_CALL_START, _FUNCTION_START))
