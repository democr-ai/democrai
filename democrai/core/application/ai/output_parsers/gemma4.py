from __future__ import annotations

import json
import logging
import re

from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.output_parsers.hermes import HermesOutputParser
from democrai.core.application.ai.output_parsers.types import ParsedModelOutput
from democrai.core.application.ai.output_parsers.types import StreamParseState


_START_TOKEN = "<|channel>"
_END_TOKEN = "<channel|>"
_THOUGHT_PREFIX = "thought\n"
_BARE_THOUGHT_RE = re.compile(r"^\s*thought(?:\s+|$)", re.IGNORECASE)
_LEGACY_THOUGHT_STARTS = ("<thought>", "<thought\n", "<think>", "<think\n")
_LEGACY_THOUGHT_ENDS = ("</thought>", "</think>")
_TOOL_STARTS = ("<|tool_call>", "<|tool_call|>")
_TOOL_END = "<tool_call|>"
_QUOTE = '<|"|>'
_ORPHAN_CONTENT_PREFIXES = (_TOOL_END, _QUOTE)
_PARSE_ERROR_TOOL = "__democrai_tool_parse_error__"
_LOGGER = logging.getLogger(__name__)


class Gemma4OutputParser(HermesOutputParser):
    def parse(self, text: str) -> ParsedModelOutput:
        reasoning, content = _gemma4_reasoning_content(text)
        parsed = super().parse(content or "")
        if not parsed.tool_calls:
            parsed = _parse_gemma4_tool_calls(content or "")
        return ParsedModelOutput(
            content=parsed.content,
            reasoning=reasoning,
            tool_calls=parsed.tool_calls,
        )

    def feed(self, state: StreamParseState, text: str) -> list[ParsedModelOutput]:
        if not text:
            return []
        state.buffer += text
        if _buffer_starts_with_tool_call(state.buffer):
            if _TOOL_END not in state.buffer:
                return []
            parsed = _parse_gemma4_tool_calls(state.buffer)
            state.buffer = ""
            return [parsed]
        return _stream_deltas(state)

    def finish(self, state: StreamParseState) -> list[ParsedModelOutput]:
        if _buffer_starts_with_tool_call(state.buffer):
            parsed = _parse_gemma4_tool_calls(state.buffer)
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
    if not pending_marker and not finishing and _should_wait_for_bare_channel_end(state.buffer):
        return []
    reasoning, content = _gemma4_reasoning_content(state.buffer)
    content = _strip_orphan_content_prefixes(content)
    if _has_pending_tool_call(content or ""):
        content = None
        parsed_tool_calls: list[ToolCall] = []
    else:
        parsed_content = _parse_gemma4_tool_calls(content or "")
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


def _gemma4_reasoning_content(text: str) -> tuple[str | None, str | None]:
    raw = str(text or "")
    legacy = _legacy_reasoning_content(raw)
    if legacy is not None:
        return legacy
    bare_thought = _bare_thought_reasoning_content(raw)
    if bare_thought is not None:
        return bare_thought
    bare_channel = _bare_channel_reasoning_content(raw)
    if bare_channel is not None:
        return bare_channel
    if _START_TOKEN not in raw:
        if _START_TOKEN.startswith(raw.lstrip()):
            return None, None
        return None, raw or None

    before_start, _, after_start = raw.partition(_START_TOKEN)
    if _END_TOKEN not in after_start:
        reasoning = _strip_thought_label(after_start)
        return reasoning.strip() or None, before_start or None

    reasoning, _, content = after_start.partition(_END_TOKEN)
    visible_reasoning = _strip_thought_label(reasoning).strip() or None
    visible_content = f"{before_start}{content.lstrip()}".strip() or None
    return visible_reasoning, visible_content


def _legacy_reasoning_content(text: str) -> tuple[str | None, str | None] | None:
    start_index = -1
    start_marker = ""
    for marker in _LEGACY_THOUGHT_STARTS:
        current = text.find(marker)
        if current >= 0 and (start_index < 0 or current < start_index):
            start_index = current
            start_marker = marker
    if start_index < 0:
        return None

    before = text[:start_index]
    after_start = text[start_index + len(start_marker) :]
    end_index = -1
    end_marker = ""
    for marker in _LEGACY_THOUGHT_ENDS:
        current = after_start.find(marker)
        if current >= 0 and (end_index < 0 or current < end_index):
            end_index = current
            end_marker = marker
    if end_index < 0:
        return after_start.strip() or None, before.strip() or None

    reasoning = after_start[:end_index]
    content = before + after_start[end_index + len(end_marker) :]
    return reasoning.strip() or None, content.strip() or None


def _bare_thought_reasoning_content(text: str) -> tuple[str | None, str | None] | None:
    match = _BARE_THOUGHT_RE.match(str(text or ""))
    if match is None:
        return None
    after_label = text[match.end() :]
    if _END_TOKEN not in after_label:
        return after_label.strip() or None, None
    reasoning, _, content = after_label.partition(_END_TOKEN)
    return reasoning.strip() or None, content.strip() or None


def _bare_channel_reasoning_content(text: str) -> tuple[str | None, str | None] | None:
    raw = str(text or "")
    if _END_TOKEN not in raw or _START_TOKEN in raw:
        return None
    reasoning, _, content = raw.partition(_END_TOKEN)
    return reasoning.strip() or None, content.strip() or None


def _should_wait_for_bare_channel_end(text: str) -> bool:
    raw = str(text or "")
    if not raw or _START_TOKEN in raw or _END_TOKEN in raw:
        return False
    if _buffer_starts_with_tool_call(raw):
        return False
    return True


def _strip_thought_label(text: str) -> str:
    if text.startswith(_THOUGHT_PREFIX):
        return text[len(_THOUGHT_PREFIX) :]
    return text


def _is_empty_thought_label(text: str | None) -> bool:
    return str(text or "").strip().lower() == "thought"


def _parse_gemma4_tool_calls(text: str) -> ParsedModelOutput:
    text = _strip_orphan_content_prefixes(text) or ""
    start_pattern = "|".join(re.escape(marker) for marker in _TOOL_STARTS)
    matches = re.findall(
        rf"(?:{start_pattern})(.*?){re.escape(_TOOL_END)}",
        text,
        flags=re.DOTALL,
    )
    open_tool_call = ""
    open_marker = next(
        (marker for marker in _TOOL_STARTS if text.lstrip().startswith(marker)),
        "",
    )
    if not matches and open_marker:
        open_tool_call = text.lstrip()[len(open_marker) :]
        matches = [open_tool_call]
    tool_calls: list[ToolCall] = []
    for index, item in enumerate(matches):
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
            _LOGGER.warning(
                "Gemma4 tool call parse failed: %s raw=%r",
                exc,
                item,
            )
            tool_calls.append(
                ToolCall(
                    id=f"tool_call_{index}",
                    type="function",
                    function_name=_PARSE_ERROR_TOOL,
                    arguments=json.dumps(
                        {
                            "status": "error",
                            "error": "gemma4_tool_call_invalid",
                            "message": "The model emitted a tool call that could not be parsed.",
                            "raw": item,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
    if not tool_calls:
        return ParsedModelOutput(content=text or None)
    if open_tool_call:
        content = text[: text.find(open_marker)].strip()
    else:
        content = re.sub(
            rf"(?:{start_pattern}).*?{re.escape(_TOOL_END)}",
            "",
            text,
            flags=re.DOTALL,
        ).strip()
    return ParsedModelOutput(content=content or None, tool_calls=tool_calls)


def _strip_orphan_content_prefixes(text: str | None) -> str | None:
    if not text:
        return text
    raw = str(text)
    leading_len = len(raw) - len(raw.lstrip())
    leading = raw[:leading_len]
    content = raw[leading_len:]
    stripped = False
    while True:
        marker = next(
            (
                candidate
                for candidate in _ORPHAN_CONTENT_PREFIXES
                if content.startswith(candidate)
            ),
            None,
        )
        if marker is None:
            break
        content = content[len(marker) :].lstrip()
        stripped = True
    if not stripped:
        return raw
    return f"{leading}{content}".strip() or None


def _buffer_starts_with_tool_call(text: str) -> bool:
    raw = str(text or "").lstrip()
    return any(raw.startswith(marker) for marker in _TOOL_STARTS)


def _has_pending_tool_call(text: str) -> bool:
    raw = str(text or "")
    if not raw:
        return False
    last_marker = max(raw.rfind(marker) for marker in _TOOL_STARTS)
    if last_marker >= 0:
        return _TOOL_END not in raw[last_marker:]
    last_open = raw.rfind("<|")
    if last_open < 0:
        return False
    suffix = raw[last_open:].lstrip()
    return any(marker.startswith(suffix) for marker in _TOOL_STARTS)


def _has_pending_legacy_reasoning_marker(text: str) -> bool:
    raw = str(text or "").lstrip()
    if raw in {"<", "</"}:
        return True
    markers = (*_LEGACY_THOUGHT_STARTS, *_LEGACY_THOUGHT_ENDS)
    return any(marker.startswith(raw) and raw != marker for marker in markers)


def _has_pending_bare_reasoning_marker(text: str) -> bool:
    raw = str(text or "").lstrip().lower()
    if not raw:
        return False
    return "thought".startswith(raw) and raw != "thought"


def _split_pending_reasoning_marker(text: str) -> tuple[str, str]:
    raw = str(text or "")
    if not raw:
        return raw, ""
    markers = (_START_TOKEN, *_LEGACY_THOUGHT_STARTS, *_LEGACY_THOUGHT_ENDS)
    for index in range(max(len(raw) - max(len(marker) for marker in markers) + 1, 0), len(raw)):
        suffix = raw[index:]
        if not suffix:
            continue
        if any(marker.startswith(suffix) and marker != suffix for marker in markers):
            return raw[:index], suffix
    return raw, ""


def _parse_gemma4_tool_payload(text: str) -> tuple[str, dict[str, object]]:
    raw = text.strip()
    match = re.match(r"call:([^{]+)\{(.*)\}\s*$", raw, flags=re.DOTALL)
    if match is None:
        raise ValueError("gemma4_tool_call_invalid")
    name = match.group(1).strip()
    return name, _parse_gemma4_object_body(_unwrap_gemma4_object_body(match.group(2)))


def _unwrap_gemma4_object_body(text: str) -> str:
    raw = text.strip()
    if not raw.startswith("{") or not raw.endswith("}"):
        return text
    inner = raw[1:-1].strip()
    if not inner:
        return text
    try:
        _split_gemma4_pair(inner)
    except ValueError:
        return text
    return inner


def _parse_gemma4_object_body(text: str) -> dict[str, object]:
    arguments: dict[str, object] = {}
    for item in _split_gemma4_items(text):
        key, value = _split_gemma4_pair(item)
        arguments[_parse_gemma4_key(key)] = _parse_gemma4_value(value)
    return arguments


def _split_gemma4_pair(text: str) -> tuple[str, str]:
    quote_marker = ""
    depth = 0
    index = 0
    while index < len(text):
        if text.startswith(_QUOTE, index):
            quote_marker = "" if quote_marker == _QUOTE else _QUOTE
            index += len(_QUOTE)
            continue
        char = text[index]
        if char == '"' and quote_marker != _QUOTE and not _is_escaped(text, index):
            quote_marker = "" if quote_marker == '"' else '"'
            index += 1
            continue
        if not quote_marker:
            if char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
            elif char == ":" and depth == 0:
                return text[:index], text[index + 1 :]
        index += 1
    raise ValueError("gemma4_tool_call_invalid")


def _split_gemma4_items(text: str) -> list[str]:
    items: list[str] = []
    start = 0
    quote_marker = ""
    depth = 0
    index = 0
    while index < len(text):
        if text.startswith(_QUOTE, index):
            quote_marker = "" if quote_marker == _QUOTE else _QUOTE
            index += len(_QUOTE)
            continue
        char = text[index]
        if char == '"' and quote_marker != _QUOTE and not _is_escaped(text, index):
            quote_marker = "" if quote_marker == '"' else '"'
            index += 1
            continue
        if not quote_marker:
            if char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
            elif char == "," and depth == 0:
                item = text[start:index].strip()
                if item:
                    items.append(item)
                start = index + 1
        index += 1
    item = text[start:].strip()
    if item:
        items.append(item)
    return items


def _parse_gemma4_key(text: str) -> str:
    raw = text.strip()
    if raw.startswith(_QUOTE) and raw.endswith(_QUOTE):
        return raw[len(_QUOTE) : -len(_QUOTE)]
    if raw.startswith('"') and raw.endswith('"'):
        try:
            return str(json.loads(raw))
        except ValueError:
            return raw[1:-1]
    return raw


def _parse_gemma4_value(text: str) -> object:
    raw = text.strip()
    if raw.startswith(_QUOTE) and raw.endswith(_QUOTE):
        return raw[len(_QUOTE) : -len(_QUOTE)]
    if raw.startswith('"') and raw.endswith('"'):
        try:
            return json.loads(raw)
        except ValueError:
            return raw[1:-1]
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw == "null":
        return None
    if raw.startswith("{") and raw.endswith("}"):
        return _parse_gemma4_object_body(raw[1:-1])
    if raw.startswith("[") and raw.endswith("]"):
        return [_parse_gemma4_value(item) for item in _split_gemma4_items(raw[1:-1])]
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return bool(slash_count % 2)
