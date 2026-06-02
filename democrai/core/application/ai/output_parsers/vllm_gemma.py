from __future__ import annotations

import json
import logging
import re

from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.output_parsers.base import ModelOutputParser
from democrai.core.application.ai.output_parsers.gemma4 import _gemma4_reasoning_content
from democrai.core.application.ai.output_parsers.gemma4 import _has_pending_bare_reasoning_marker
from democrai.core.application.ai.output_parsers.gemma4 import _has_pending_legacy_reasoning_marker
from democrai.core.application.ai.output_parsers.gemma4 import _is_empty_thought_label
from democrai.core.application.ai.output_parsers.gemma4 import _parse_gemma4_tool_payload
from democrai.core.application.ai.output_parsers.gemma4 import _should_wait_for_bare_channel_end
from democrai.core.application.ai.output_parsers.gemma4 import _split_pending_reasoning_marker
from democrai.core.application.ai.output_parsers.gemma4 import _strip_orphan_content_prefixes
from democrai.core.application.ai.output_parsers.types import ParsedModelOutput
from democrai.core.application.ai.output_parsers.types import StreamParseState


_LOGGER = logging.getLogger(__name__)
_WRAPPED_TOOL_STARTS = ("<|tool_call>", "<|tool_call|>")
_WRAPPED_TOOL_END = "<tool_call|>"
_RAW_TOOL_PREFIX = "call:"
_PARSE_ERROR_TOOL = "__democrai_tool_parse_error__"


class VllmGemmaOutputParser(ModelOutputParser):
    def parse(self, text: str) -> ParsedModelOutput:
        reasoning, content = _gemma4_reasoning_content(text)
        reasoning, content = _split_inline_vllm_gemma_reasoning(reasoning, content)
        parsed = _parse_vllm_gemma_tool_calls(content or "")
        return ParsedModelOutput(
            content=parsed.content,
            reasoning=reasoning,
            tool_calls=parsed.tool_calls,
        )

    def feed(self, state: StreamParseState, text: str) -> list[ParsedModelOutput]:
        if not text:
            return []
        state.buffer += text
        if _buffer_starts_with_vllm_gemma_tool_call(state.buffer):
            if _has_pending_vllm_gemma_tool_call(state.buffer):
                return []
            parsed = _parse_vllm_gemma_tool_calls(state.buffer)
            state.buffer = ""
            return [parsed]
        return _stream_deltas(state)

    def finish(self, state: StreamParseState) -> list[ParsedModelOutput]:
        if _buffer_starts_with_vllm_gemma_tool_call(state.buffer):
            parsed = _parse_vllm_gemma_tool_calls(state.buffer)
            state.buffer = ""
            return [parsed]
        state.finishing = True
        outputs = _stream_deltas(state)
        state.buffer = ""
        state.finishing = False
        return outputs


def _stream_deltas(state: StreamParseState) -> list[ParsedModelOutput]:
    if _has_pending_legacy_reasoning_marker(state.buffer) or _has_pending_bare_reasoning_marker(state.buffer):
        return []
    safe_buffer, pending_marker = _split_pending_reasoning_marker(state.buffer)
    if pending_marker:
        state.buffer = safe_buffer
    finishing = bool(getattr(state, "finishing", False))
    if (
        not pending_marker
        and not finishing
        and _should_wait_for_bare_channel_end(state.buffer)
        and not _starts_with_inline_vllm_gemma_reasoning(state.buffer)
    ):
        return []
    reasoning, content = _gemma4_reasoning_content(state.buffer)
    reasoning, content = _split_inline_vllm_gemma_reasoning(reasoning, content)
    content = _strip_orphan_content_prefixes(content)
    if _has_pending_vllm_gemma_tool_call(content or ""):
        content = None
        parsed_tool_calls: list[ToolCall] = []
    else:
        parsed_content = _parse_vllm_gemma_tool_calls(content or "")
        content = parsed_content.content
        parsed_tool_calls = parsed_content.tool_calls
    emitted_reasoning_len = int(getattr(state, "emitted_reasoning_len", 0) or 0)
    emitted_content_len = int(getattr(state, "emitted_content_len", 0) or 0)
    emitted_tool_call_count = int(getattr(state, "emitted_tool_call_count", 0) or 0)
    if reasoning and content and emitted_content_len > len(content):
        emitted_content_len = 0
    reasoning_delta = (
        reasoning[emitted_reasoning_len:]
        if reasoning and len(reasoning) > emitted_reasoning_len
        else None
    )
    if _is_empty_thought_label(reasoning_delta):
        reasoning_delta = None
    content_delta = (
        content[emitted_content_len:]
        if content and len(content) > emitted_content_len
        else None
    )
    if reasoning:
        state.emitted_reasoning_len = len(reasoning)
    if content:
        state.emitted_content_len = len(content)
    tool_call_delta = parsed_tool_calls[emitted_tool_call_count:]
    if parsed_tool_calls:
        state.emitted_tool_call_count = len(parsed_tool_calls)
    if pending_marker:
        state.buffer = f"{state.buffer}{pending_marker}"
    if not reasoning_delta and not content_delta and not tool_call_delta:
        return []
    return [
        ParsedModelOutput(
            content=content_delta,
            reasoning=reasoning_delta,
            tool_calls=tool_call_delta,
        )
    ]


def _parse_vllm_gemma_tool_calls(text: str) -> ParsedModelOutput:
    text = _strip_orphan_content_prefixes(text) or ""
    wrapped_start_pattern = "|".join(re.escape(marker) for marker in _WRAPPED_TOOL_STARTS)
    wrapped_matches = re.findall(
        rf"(?:{wrapped_start_pattern})(.*?){re.escape(_WRAPPED_TOOL_END)}",
        text,
        flags=re.DOTALL,
    )
    raw_match = ""
    if not wrapped_matches and text.lstrip().startswith(_RAW_TOOL_PREFIX):
        raw_match = text.lstrip()
        wrapped_matches = [raw_match]
    tool_calls: list[ToolCall] = []
    for index, item in enumerate(wrapped_matches):
        try:
            name, arguments = _parse_gemma4_tool_payload(item)
            tool_calls.append(
                ToolCall(
                    id=f"tool_call_{index}",
                    type="function",
                    function_name=name,
                    arguments=json.dumps(arguments, ensure_ascii=False),
                )
            )
        except ValueError as exc:
            _LOGGER.warning("vLLM Gemma tool call parse failed: %s raw=%r", exc, item)
            tool_calls.append(
                ToolCall(
                    id=f"tool_call_{index}",
                    type="function",
                    function_name=_PARSE_ERROR_TOOL,
                    arguments=json.dumps(
                        {
                            "status": "error",
                            "error": "vllm_gemma_tool_call_invalid",
                            "message": "The model emitted a tool call that could not be parsed.",
                            "raw": item,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
    if not tool_calls:
        return ParsedModelOutput(content=text or None)
    if raw_match:
        return ParsedModelOutput(content=None, tool_calls=tool_calls)
    content = re.sub(
        rf"(?:{wrapped_start_pattern}).*?{re.escape(_WRAPPED_TOOL_END)}",
        "",
        text,
        flags=re.DOTALL,
    ).strip()
    return ParsedModelOutput(content=content or None, tool_calls=tool_calls)


def _buffer_starts_with_vllm_gemma_tool_call(text: str) -> bool:
    raw = str(text or "").lstrip()
    return raw.startswith(_RAW_TOOL_PREFIX) or any(raw.startswith(marker) for marker in _WRAPPED_TOOL_STARTS)


def _has_pending_vllm_gemma_tool_call(text: str) -> bool:
    raw = str(text or "")
    if not raw:
        return False
    stripped = raw.lstrip()
    if stripped.startswith(_RAW_TOOL_PREFIX):
        try:
            _parse_gemma4_tool_payload(stripped)
        except ValueError:
            return True
        return False
    last_marker = max(raw.rfind(marker) for marker in _WRAPPED_TOOL_STARTS)
    if last_marker >= 0:
        return _WRAPPED_TOOL_END not in raw[last_marker:]
    last_open = raw.rfind("<|")
    if last_open < 0:
        return False
    suffix = raw[last_open:].lstrip()
    return any(marker.startswith(suffix) for marker in _WRAPPED_TOOL_STARTS)


def _split_inline_vllm_gemma_reasoning(
    reasoning: str | None,
    content: str | None,
) -> tuple[str | None, str | None]:
    if content:
        return reasoning, content
    raw_reasoning = str(reasoning or "").strip()
    if not raw_reasoning:
        return reasoning, content
    final_answer = _split_final_answer_reasoning(raw_reasoning)
    if final_answer is not None:
        return final_answer
    final_output = _split_final_output_generation_reasoning(raw_reasoning)
    if final_output is not None:
        return final_output
    return reasoning, content


def _split_final_answer_reasoning(
    raw_reasoning: str,
) -> tuple[str | None, str | None] | None:
    match = re.search(
        r"(?is)^(.*?)(?:\*\*)?final answer:\s*(?:\*\*)?\s*(.+?)\s*$",
        raw_reasoning,
    )
    if match is None:
        return None
    visible_reasoning = match.group(1).rstrip()
    visible_content = match.group(2).strip()
    if visible_reasoning.endswith("**"):
        visible_reasoning = visible_reasoning[:-2].rstrip()
    return visible_reasoning or None, visible_content or None


def _split_final_output_generation_reasoning(
    raw_reasoning: str,
) -> tuple[str | None, str | None] | None:
    marker_match = re.search(r"(?is)final output generation:\s*", raw_reasoning)
    if marker_match is None:
        return None
    section = raw_reasoning[marker_match.end() :]
    candidate_match = re.search(r"(?s)(?:\)\s*|]\s*|}\s*)([^\n]+?)\s*$", section)
    if candidate_match is None:
        return None
    visible_content = candidate_match.group(1).strip()
    if not visible_content:
        return None
    visible_reasoning = raw_reasoning[: marker_match.end()] + section[: candidate_match.start()]
    return visible_reasoning.rstrip() or None, visible_content


def _starts_with_inline_vllm_gemma_reasoning(text: str | None) -> bool:
    raw = str(text or "").lstrip().lower()
    return raw.startswith("thought\n") or raw.startswith("thinking process:") or raw.startswith("here's a thinking process:")
