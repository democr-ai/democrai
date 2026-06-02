from __future__ import annotations

import json
import re
from hashlib import sha1

from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.output_parsers.base import ModelOutputParser
from democrai.core.application.ai.output_parsers.types import ParsedModelOutput
from democrai.core.application.ai.output_parsers.types import StreamParseState


_SEGMENT_RE = re.compile(
    r"(?:<\|start\|>assistant)?<\|channel\|>(?P<channel>analysis|final|commentary)"
    r"(?:\s+to=(?P<target>[^<\s]+))?"
    r"(?:\s+<\|constrain\|>json)?"
    r"(?:<\|message\|>)?(?P<body>.*?)(?=<\|end\|>|<\|start\|>|"
    r"<\|channel\|>(?:analysis|final|commentary)(?:\s+to=[^<\s]+)?"
    r"(?:\s+<\|constrain\|>json)?(?:<\|message\|>)?|$)",
    flags=re.DOTALL,
)
_LEADING_CHANNEL_FRAGMENT_RE = re.compile(
    r"^\s*(?:<\|start\|>assistant)?<\|channel\|>"
    r"(?:analysis|analys|analy|anal|ana|an|a|final|fina|fin|fi|f)?\s*",
    flags=re.DOTALL,
)
_TRAILING_CHANNEL_FRAGMENT_RE = re.compile(
    r"\s*(?:<\|start\|>assistant)?<\|channel\|>"
    r"(?:analysis|analys|analy|anal|ana|an|a|final|fina|fin|fi|f)?\s*$",
    flags=re.DOTALL,
)


class GptOssOutputParser(ModelOutputParser):
    def parse(self, text: str) -> ParsedModelOutput:
        return _gpt_oss_parse(text)

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
    parsed = _gpt_oss_parse(state.buffer)
    reasoning = parsed.reasoning
    content = parsed.content
    tool_calls = parsed.tool_calls

    emitted_reasoning_len = int(getattr(state, "emitted_reasoning_len", 0) or 0)
    emitted_content_len = int(getattr(state, "emitted_content_len", 0) or 0)
    emitted_tool_call_count = int(getattr(state, "emitted_tool_call_count", 0) or 0)
    reasoning_delta = (
        reasoning[emitted_reasoning_len:]
        if reasoning and len(reasoning) > emitted_reasoning_len
        else None
    )
    content_delta = (
        content[emitted_content_len:]
        if content and len(content) > emitted_content_len
        else None
    )
    output = ParsedModelOutput(
        content=content_delta,
        reasoning=reasoning_delta,
        tool_calls=tool_calls[emitted_tool_call_count:],
    )
    if reasoning:
        state.emitted_reasoning_len = len(reasoning)
    if content:
        state.emitted_content_len = len(content)
    if tool_calls:
        state.emitted_tool_call_count = len(tool_calls)
    if not output.content and not output.reasoning and not output.tool_calls:
        return []
    return [output]


def _gpt_oss_parse(text: str) -> ParsedModelOutput:
    raw = str(text or "")
    if "<|channel|>" not in raw:
        return ParsedModelOutput(content=raw or None)

    reasoning_parts: list[str] = []
    final_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for match in _SEGMENT_RE.finditer(raw):
        channel = str(match.group("channel") or "").strip().lower()
        target = str(match.group("target") or "").strip()
        body = _clean_body(match.group("body"))
        if not body:
            continue
        if channel == "analysis":
            reasoning_parts.append(body)
        elif channel == "final":
            final_parts.append(body)
        elif channel == "commentary":
            tool_call = _tool_call_from_commentary(target, body)
            if tool_call is not None:
                tool_calls.append(tool_call)

    reasoning = _clean_visible_text("\n\n".join(reasoning_parts)) or None
    content = _clean_visible_text("".join(final_parts)) or None
    return ParsedModelOutput(
        content=content,
        reasoning=reasoning,
        tool_calls=tool_calls,
    )


def _tool_call_from_commentary(target: str, body: str) -> ToolCall | None:
    prefix = "functions."
    if not target.startswith(prefix):
        return None
    function_name = target[len(prefix):].strip()
    if not function_name:
        return None
    arguments = _json_arguments(body)
    if arguments is None:
        return None
    digest = sha1(f"{function_name}:{arguments}".encode("utf-8")).hexdigest()[:12]
    return ToolCall(
        id=f"gpt_oss_{digest}",
        function_name=function_name,
        arguments=arguments,
    )


def _json_arguments(body: str) -> str | None:
    cleaned = _clean_body(body)
    if not cleaned:
        return None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return json.dumps(parsed, ensure_ascii=True)


def _clean_body(value: str) -> str:
    return re.sub(r"<\|end\|>\s*$", "", str(value or ""), flags=re.DOTALL).strip()


def _clean_visible_text(value: str) -> str:
    cleaned = _clean_body(value)
    cleaned = _LEADING_CHANNEL_FRAGMENT_RE.sub("", cleaned)
    cleaned = _TRAILING_CHANNEL_FRAGMENT_RE.sub("", cleaned)
    return cleaned.strip()
