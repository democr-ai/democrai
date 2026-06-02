from __future__ import annotations

import json
import re

from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.output_parsers.base import ModelOutputParser
from democrai.core.application.ai.output_parsers.types import ParsedModelOutput
from democrai.core.application.ai.output_parsers.types import StreamParseState


class HermesOutputParser(ModelOutputParser):
    def parse(self, text: str) -> ParsedModelOutput:
        content, tool_calls = _parse_hermes_tool_calls(text)
        return ParsedModelOutput(content=content, tool_calls=tool_calls)

    def feed(self, state: StreamParseState, text: str) -> list[ParsedModelOutput]:
        if not text:
            return []
        candidate = state.buffer + text
        if _should_buffer_hermes_tool_call_fragment(candidate):
            state.buffer += text
            return []
        parsed = self.parse(candidate)
        if parsed.tool_calls:
            state.buffer = ""
            return [parsed]
        if state.buffer:
            state.buffer = ""
            return [ParsedModelOutput(content=candidate)]
        return [ParsedModelOutput(content=text)]


def _parse_hermes_tool_calls(text: str) -> tuple[str | None, list[ToolCall]]:
    matches = re.findall(r"<tool_call>(.*?)</tool_call>", text, flags=re.DOTALL)
    open_tool_call = ""
    if not matches and text.lstrip().startswith("<tool_call>"):
        open_tool_call = text.lstrip()[len("<tool_call>") :]
        matches = [open_tool_call]
    tool_calls = [
        ToolCall(
            id=f"tool_call_{index}",
            type="function",
            function_name=name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        )
        for index, item in enumerate(matches)
        for name, arguments in [_parse_hermes_tool_payload(item)]
    ]
    if not tool_calls:
        return text, []
    if open_tool_call:
        content = text[: text.find("<tool_call>")].strip()
    else:
        content = re.sub(
            r"<tool_call>.*?</tool_call>",
            "",
            text,
            flags=re.DOTALL,
        ).strip()
    return content or None, tool_calls


def _parse_hermes_tool_payload(text: str) -> tuple[str, dict[str, object]]:
    raw = text.strip()
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    if payload is not None:
        return payload["name"], payload["arguments"]

    function_match = re.search(r"<function=([^>]+)>", raw)
    if function_match is None:
        raise ValueError("hermes_tool_call_invalid")
    name = function_match.group(1).strip()
    body = raw[function_match.end() :]
    end_index = body.find("</function>")
    if end_index >= 0:
        body = body[:end_index]
    return name, _parse_hermes_parameters(body)


def _parse_hermes_parameters(text: str) -> dict[str, object]:
    arguments: dict[str, object] = {}
    matches = list(
        re.finditer(
            r"<parameter=([^>]+)>(.*?)(?=<parameter=|</function>|$)",
            text,
            flags=re.DOTALL,
        )
    )
    for match in matches:
        name = match.group(1).strip()
        if name:
            value = re.sub(r"</parameter>\s*$", "", match.group(2), flags=re.DOTALL)
            arguments[name] = _parse_hermes_parameter(value)
    return arguments


def _parse_hermes_parameter(value: str) -> object:
    text = value.strip()
    if not text:
        return ""
    if text[0] not in '[{"0123456789tfn-':
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def _should_buffer_hermes_tool_call_fragment(text: str) -> bool:
    raw = text.lstrip()
    marker = "<tool_call>"
    if marker.startswith(raw):
        return True
    if not raw.startswith(marker):
        return False
    return "</tool_call>" not in raw
