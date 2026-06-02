from __future__ import annotations

from democrai.core.application.ai.engine.pipeline.tool_aliases import (
    resolve_tool_call_name,
)
from democrai.core.application.ai.engine.pipeline.tool_aliases import tool_wire_name


def test_resolve_tool_call_name_maps_underscore_to_dot_variant():
    runtime_name = "agent.chat.component-agent"
    wire_name = tool_wire_name(runtime_name)
    alias_map = {wire_name: runtime_name}

    assert wire_name == "agent_chat_component-agent_72091346a0"
    assert (
        resolve_tool_call_name(
            "agent_chat_component-agent_72091346a0",
            alias_map,
        )
        == runtime_name
    )


def test_tool_wire_name_preserves_hyphen_and_maps_dot_to_underscore():
    assert (
        tool_wire_name("chat.list-attachments")
        == "chat_list-attachments_4c4daf7167"
    )
