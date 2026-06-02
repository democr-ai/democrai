from __future__ import annotations

from typing import Any

from democrai.sdk.decorators import tool


@tool(
    "test-echo",
    title="Test tool",
    description="Return the provided text with a fixed test marker.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to echo.",
            },
        },
        "required": ["text"],
    },
)
def test_echo(text: str = "") -> dict[str, Any]:
    return {"text": text, "marker": "system_test_tool"}
