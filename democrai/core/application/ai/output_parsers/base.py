from __future__ import annotations

from democrai.core.application.ai.output_parsers.types import ParsedModelOutput
from democrai.core.application.ai.output_parsers.types import StreamParseState


class ModelOutputParser:
    def parse(self, text: str) -> ParsedModelOutput:
        return ParsedModelOutput(content=text or None)

    def new_stream_state(self) -> StreamParseState:
        return StreamParseState()

    def feed(self, state: StreamParseState, text: str) -> list[ParsedModelOutput]:
        if not text:
            return []
        if state.buffer:
            text = state.buffer + text
            state.buffer = ""
        return [self.parse(text)]

    def finish(self, state: StreamParseState) -> list[ParsedModelOutput]:
        if not state.buffer:
            return []
        text = state.buffer
        state.buffer = ""
        return [self.parse(text)]
