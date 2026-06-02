from __future__ import annotations

from democrai.core.application.ai.output_parsers.hermes import HermesOutputParser
from democrai.core.application.ai.output_parsers.hermes import _should_buffer_hermes_tool_call_fragment
from democrai.core.application.ai.output_parsers.types import ParsedModelOutput
from democrai.core.application.ai.output_parsers.types import StreamParseState


class Qwen3OutputParser(HermesOutputParser):
    def parse(self, text: str) -> ParsedModelOutput:
        reasoning, content = _qwen3_reasoning_content(text)
        if not content:
            return ParsedModelOutput(reasoning=reasoning)
        parsed = super().parse(content or "")
        return ParsedModelOutput(
            content=parsed.content,
            reasoning=reasoning,
            tool_calls=parsed.tool_calls,
        )

    def feed(self, state: StreamParseState, text: str) -> list[ParsedModelOutput]:
        if not text:
            return []
        state.buffer += text
        return _stream_deltas(self, state)

    def finish(self, state: StreamParseState) -> list[ParsedModelOutput]:
        outputs = _stream_deltas(self, state)
        state.buffer = ""
        return outputs


def _stream_deltas(
    parser: Qwen3OutputParser,
    state: StreamParseState,
) -> list[ParsedModelOutput]:
    raw = str(state.buffer or "")
    if not raw.strip():
        return []
    if _pending_think_start(raw) or _pending_reasoning_marker_start(raw):
        return []

    reasoning, content = _qwen3_reasoning_content(raw)
    if content and _should_buffer_hermes_tool_call_fragment(content):
        return []
    parsed = HermesOutputParser.parse(parser, content or "")
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


def _qwen3_reasoning_content(text: str) -> tuple[str | None, str | None]:
    raw = text or ""
    if "<think>" in raw:
        raw = raw.partition("<think>")[2]
    if "</think>" in raw:
        reasoning, _, content = raw.partition("</think>")
        return reasoning.strip() or None, content.strip() or None
    if "<think>" in text:
        return raw.strip() or None, None
    if _starts_with_reasoning_marker(raw):
        return raw.strip(), None
    return None, raw


def _pending_think_start(text: str) -> bool:
    raw = str(text or "").lstrip()
    marker = "<think>"
    return bool(raw and marker.startswith(raw) and raw != marker)


def _pending_reasoning_marker_start(text: str) -> bool:
    raw = str(text or "").lstrip()
    return any(raw and marker.startswith(raw) and raw != marker for marker in _REASONING_MARKERS)


def _starts_with_reasoning_marker(text: str) -> bool:
    raw = str(text or "").lstrip()
    return any(raw.startswith(marker) for marker in _REASONING_MARKERS)


_REASONING_MARKERS = (
    "Thinking Process:",
    "Here's a thinking process:",
)
