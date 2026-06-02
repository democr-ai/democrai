from __future__ import annotations

import json

from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.output_parsers.base import ModelOutputParser
from democrai.core.application.ai.output_parsers.types import ParsedModelOutput
from democrai.core.application.ai.output_parsers.types import StreamParseState


class Llama31OutputParser(ModelOutputParser):
    def parse(self, text: str) -> ParsedModelOutput:
        tool_call = _parse_llama31_tool_call(text)
        if tool_call is None:
            return ParsedModelOutput(content=text or None)
        return ParsedModelOutput(tool_calls=[tool_call])

    def feed(self, state: StreamParseState, text: str) -> list[ParsedModelOutput]:
        if not text:
            return []
        state.buffer += text
        raw = str(state.buffer or "")
        if not raw.lstrip().startswith("{"):
            state.buffer = ""
            return [ParsedModelOutput(content=raw)]
        tool_call = _parse_llama31_tool_call(raw)
        if tool_call is None:
            if _looks_like_incomplete_json(raw):
                return []
            state.buffer = ""
            return [ParsedModelOutput(content=raw)]
        state.buffer = ""
        return [ParsedModelOutput(tool_calls=[tool_call])]

    def finish(self, state: StreamParseState) -> list[ParsedModelOutput]:
        if not state.buffer:
            return []
        raw = str(state.buffer or "")
        state.buffer = ""
        return [self.parse(raw)]


def _parse_llama31_tool_call(text: str) -> ToolCall | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("name") or "").strip()
    parameters = payload.get("parameters")
    if not name or not isinstance(parameters, dict):
        return None
    return ToolCall(
        id="tool_call_0",
        type="function",
        function_name=name,
        arguments=json.dumps(parameters, ensure_ascii=False),
    )


def _looks_like_incomplete_json(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return raw.startswith("{")
    return False
