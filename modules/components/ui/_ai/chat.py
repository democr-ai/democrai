from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ...utils.ai_chat import seed_messages, seed_suggestions, seed_threads
from ..layout import shared_layout


@permission_required(["components.documentation.view"])
async def render(params: dict, session: dict) -> sdk.ui.Builder:
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/ai_chat"), components=True)

    builder.set_store("/components_ai_chat/messages", seed_messages(), scope="page")
    builder.set_data("/components_ai/chat/threads", seed_threads())
    builder.set_data("/components_ai/chat/suggestions", seed_suggestions())
    builder.set_data(
        "/components_ai/chat_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "messages:\n  - id: m_1\n    role: assistant\n    text: ...",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "messages:\n  type: store\n  scope: page\n  path: /components_ai_chat/messages",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Append via page store",
                "yaml": "messages:\n  type: store\n  scope: page\n  path: /components_ai_chat/messages",
                "source": "stateUpdate with full messages list",
            },
            {
                "binding": "Replace via page store",
                "yaml": "messages:\n  type: store\n  scope: page\n  path: /components_ai_chat/messages",
                "source": "stateUpdate with updated item in list",
            },
        ],
    )
    builder.set_data(
        "/components_ai/chat_cases",
        [
            {
                "case": "User text",
                "role": "user",
                "kind": "text",
                "content": "content.text, content.attachments",
                "rendering": "Right aligned bubble with attachment links",
                "update": "messages.append",
            },
            {
                "case": "Assistant text",
                "role": "assistant",
                "kind": "text",
                "content": "content.text, content.reasoning",
                "rendering": "Left aligned bubble with markdown and reasoning",
                "update": "messages.append or messages.replace",
            },
            {
                "case": "Tool result",
                "role": "tool",
                "kind": "tool_result",
                "content": "content.tool_name, content.summary",
                "rendering": "Compact tool row with status",
                "update": "messages.replace while running",
            },
            {
                "case": "Task",
                "role": "system",
                "kind": "task",
                "content": "content.task_id or content.title",
                "rendering": "Task/progress row",
                "update": "messages.replace",
            },
            {
                "case": "Component",
                "role": "assistant",
                "kind": "component",
                "content": "content.components",
                "rendering": "Flat A2UI content; add Card when framing is needed",
                "update": "messages.append or messages.replace",
            },
        ],
    )
    builder.set_data(
        "/components_ai/chat_properties",
        [
            {"property": "Row / Column layout", "type": "layout", "usage": sdk.i18n.t("components.ai.chat.property.layout")},
            {"property": "ThreadList.threads", "type": "list[dict]", "usage": sdk.i18n.t("components.ai.chat.property.threads")},
            {"property": "ThreadList.active_thread_id", "type": "str", "usage": sdk.i18n.t("components.ai.chat.property.active_thread")},
            {"property": "MessageList.messages", "type": "list[dict]", "usage": sdk.i18n.t("components.ai.chat.property.messages")},
            {"property": "Message.kind", "type": "text | component | tool_call | tool_result | task", "usage": sdk.i18n.t("components.ai.chat.property.kind")},
            {"property": "Message.content", "type": "dict", "usage": sdk.i18n.t("components.ai.chat.property.content")},
            {"property": "content.attachments", "type": "list[dict]", "usage": sdk.i18n.t("components.ai.chat.property.attachments")},
            {"property": "Suggestions.suggestions", "type": "list[dict]", "usage": sdk.i18n.t("components.ai.chat.property.suggestions")},
            {"property": "Composer.*", "type": "Composer props", "usage": sdk.i18n.t("components.ai.chat.property.composer")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_ai_chat_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
