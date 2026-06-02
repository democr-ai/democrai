from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.chat.models import Attachment, ChatComponent, Conversation, Message
from modules.chat.utils.actions.a2ui_schema import lit
from modules.chat.utils.actions.components import normalize_component_payload
from modules.chat.utils.actions.conversation import create_user_turn
from modules.chat.utils.actions.orchestration import (
    _clean_model_text,
    run_chat_orchestration,
)
from modules.chat.utils.actions.messages import next_sequence
from modules.chat.utils.ui.rows import (
    component_model_row,
)
from modules.chat.utils.ui.state import (
    THREAD_MESSAGE_PAGE_SIZE,
    THREAD_LIST_PAGE_SIZE,
    thread_messages_before,
    thread_list_state,
    visible_oldest_sequence,
)

SUMMARY_INTERVAL = 10
CHAT_OLDEST_SEQUENCE_STORE = "/chat/current/oldest_sequence"
CHAT_MESSAGES_COMPONENT = "chat_message_list"
CHAT_MESSAGES_PROPERTY = "messages"
CHAT_COMPONENT_TOOL_NAMES = {
    "chat.show-alert",
    "chat.show-badge",
    "chat.show-chart",
    "chat.show-table",
    "chat.show-list",
    "chat.show-card",
    "chat.show-collapse",
    "chat.show-metric-grid",
    "chat.show-descriptions",
    "chat.show-markdown",
    "chat.show-progress",
    "chat.show-sequence-diagram",
    "chat.show-tabs",
    "chat.show-text",
    "chat.show-title",
}


def _message_record(message: Message) -> dict[str, Any]:
    result = Message.list(filters={"id": message.id}, page=0, page_size=1)
    row = result["rows"][0]
    for key in ("created_at", "updated_at"):
        value = row.get(key)
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    return row


def _message_record_with_attachments(
    message: Message, attachments: list[dict[str, Any]]
) -> dict[str, Any]:
    row = _message_record(message)
    if attachments:
        for attachment in attachments:
            for key in ("created_at", "updated_at"):
                value = attachment.get(key)
                if hasattr(value, "isoformat"):
                    attachment[key] = value.isoformat()
        content = dict(row["content"])
        content["attachments"] = attachments
        row["content"] = content
    return row


def _message_text(message) -> str:
    content = (
        message.get("content")
        if isinstance(message, dict)
        else getattr(message, "content", None)
    )
    content = content or {}
    if isinstance(content, dict):
        return str(content.get("text") or "").strip()
    return ""


async def _generate_thread_title(module_sdk, conversation, message) -> Any:
    current_title = str(getattr(conversation, "title", "") or "").strip()
    if current_title and current_title != module_sdk.i18n.t("chat.thread.untitled"):
        return conversation
    prompt = _message_text(message)
    if not prompt:
        return conversation
    title = prompt.replace("\n", " ").strip()[:10]
    return module_sdk.database.update(
        Conversation,
        str(conversation.id),
        title=title,
    )


def _summary_input(module_sdk, conversation) -> tuple[str, int, int]:
    since_sequence = int(getattr(conversation, "summary_until_sequence", 0) or 0)
    result = Message.all(
        filters={
            "conversation_id": int(conversation.id),
            "after_sequence": since_sequence,
        },
        sort={"field": "sequence", "direction": "asc"},
    )
    messages = list(result.get("rows") or [])
    if len(messages) < SUMMARY_INTERVAL:
        return "", since_sequence, since_sequence
    lines = []
    max_sequence = since_sequence
    for row in messages:
        sequence = int(row.get("sequence") or 0)
        max_sequence = max(max_sequence, sequence)
        text = _message_text(row)
        if text:
            lines.append(f"{sequence}. {row.get('role')}: {text}")
    current_summary = str(getattr(conversation, "summary", "") or "").strip()
    prompt = (
        f"Current summary:\n{current_summary or '-'}\n\n"
        f"New messages since sequence {since_sequence}:\n" + "\n".join(lines)
    )
    return prompt, since_sequence, max_sequence


async def _refresh_thread_summary(module_sdk, conversation) -> Any:
    prompt, since_sequence, max_sequence = _summary_input(module_sdk, conversation)
    if not prompt or max_sequence <= since_sequence:
        return conversation
    result = await module_sdk.ai.run_agent(
        "chat.summary-agent",
        input=prompt,
        context={
            "source": "chat.thread.summary",
            "conversation_id": int(conversation.id),
            "summary_until_sequence": since_sequence,
        },
        max_iterations=2,
    )
    summary = _clean_model_text(str(getattr(result, "content", "") or ""))
    if not summary:
        return conversation
    return module_sdk.database.update(
        Conversation,
        str(conversation.id),
        summary=summary,
        summary_until_sequence=max_sequence,
    )


def _thread_list_data_update(
    module_sdk,
    state: dict[str, Any],
    *,
    surface_id: str,
) -> dict[str, Any]:
    return module_sdk.ui.Builder.build_data_model_update_payload(
        surface_id=surface_id,
        data={"chat": {"thread_list": state}},
    )


def _thread_list_surface_id(ctx: dict[str, Any]) -> str:
    surface_id = str(
        ctx.get("thread_list_surface_id") or ctx.get("_surface_id") or ""
    ).strip()
    if surface_id in {"", "drawer", "modal"}:
        return "main_content"
    return surface_id


async def _current_thread_list_page(
    ctx: dict[str, Any],
    module_sdk,
    *,
    surface_id: str,
) -> int:
    stream_id = str(ctx.get("stream_id") or "").strip()
    current = await module_sdk.effects.ask_current_data_value(
        stream_id,
        "/chat/thread_list/page",
        surface_id=surface_id,
    )
    return max(0, int(current or 0))


async def _current_thread_list_active_id(
    ctx: dict[str, Any],
    module_sdk,
    *,
    surface_id: str,
) -> str:
    stream_id = str(ctx.get("stream_id") or "").strip()
    current = await module_sdk.effects.ask_current_data_value(
        stream_id,
        "/chat/thread_list/active_thread_id",
        surface_id=surface_id,
    )
    return str(current or "").strip()


def _thread_list_update_messages(
    module_sdk,
    *,
    page: int,
    surface_id: str,
    active_thread_id: int | str | None = None,
) -> list[dict[str, Any]]:
    total_rows = Conversation.count()
    max_page = max(0, (total_rows - 1) // THREAD_LIST_PAGE_SIZE)
    resolved_page = min(max(0, int(page or 0)), max_page)
    state = thread_list_state(
        module_sdk,
        page=resolved_page,
        page_size=THREAD_LIST_PAGE_SIZE,
        active_thread_id=active_thread_id,
    )
    return [
        _thread_list_data_update(
            module_sdk,
            state,
            surface_id=surface_id,
        ),
        module_sdk.effects.ui_property_update(
            "chat_thread_list",
            "dataSource.data",
            state["items"],
            surface_id=surface_id,
        ),
        module_sdk.effects.ui_property_update(
            "chat_thread_page_label",
            "text",
            state["page_label"],
            surface_id=surface_id,
        ),
    ]


def _state_set(module_sdk, path: str, value: Any) -> dict[str, Any]:
    return module_sdk.ui.Builder.build_state_update_payload(
        {path: value},
        scope="page",
    )


def _message_append(module_sdk, value: Any) -> dict[str, Any]:
    return module_sdk.effects.ui_collection_append(
        CHAT_MESSAGES_COMPONENT,
        CHAT_MESSAGES_PROPERTY,
        value,
    )


def _message_prepend(module_sdk, value: Any) -> dict[str, Any]:
    return module_sdk.effects.ui_collection_prepend(
        CHAT_MESSAGES_COMPONENT,
        CHAT_MESSAGES_PROPERTY,
        value,
    )


def _message_replace(module_sdk, item_id: str, item: Any) -> dict[str, Any]:
    return module_sdk.effects.ui_collection_replace(
        CHAT_MESSAGES_COMPONENT,
        CHAT_MESSAGES_PROPERTY,
        {"id": item_id, "item": item},
    )


def _message_remove(module_sdk, item_id: str) -> dict[str, Any]:
    return module_sdk.effects.ui_collection_remove(
        CHAT_MESSAGES_COMPONENT,
        CHAT_MESSAGES_PROPERTY,
        {"id": item_id},
    )


async def _publish_message_append(module_sdk, stream_id: str, value: Any) -> None:
    await module_sdk.effects.publish_collection_append(
        stream_id,
        CHAT_MESSAGES_COMPONENT,
        CHAT_MESSAGES_PROPERTY,
        value,
    )


async def _publish_messages_scroll_bottom(module_sdk, stream_id: str) -> None:
    await module_sdk.effects.publish_property_update(
        stream_id,
        CHAT_MESSAGES_COMPONENT,
        "scroll",
        "bottom",
    )


async def _publish_message_replace(
    module_sdk,
    stream_id: str,
    item_id: str,
    item: Any,
) -> None:
    await module_sdk.effects.publish_collection_replace(
        stream_id,
        CHAT_MESSAGES_COMPONENT,
        CHAT_MESSAGES_PROPERTY,
        {"id": item_id, "item": item},
    )


async def _publish_message_remove(module_sdk, stream_id: str, item_id: str) -> None:
    await module_sdk.effects.publish_collection_remove(
        stream_id,
        CHAT_MESSAGES_COMPONENT,
        CHAT_MESSAGES_PROPERTY,
        {"id": item_id},
    )


async def _publish_toast(
    module_sdk, stream_id: str, *, level: str, message: str
) -> None:
    await module_sdk.effects.publish_ui_message(
        stream_id,
        {
            "eventNotification": {
                "kind": "toast",
                "variant": level,
                "text": message,
            }
        },
    )


async def _publish_composer_request(
    module_sdk, stream_id: str, request_id: str
) -> None:
    await module_sdk.effects.publish_property_update(
        stream_id,
        "chat_composer",
        "current_request",
        request_id,
    )


def _agent_status_row(
    row_id: str, *, title: str, text: str = "", status: str = "running"
) -> dict[str, Any]:
    return {
        "id": row_id,
        "role": "system",
        "kind": "task",
        "status": status,
        "content": {"title": title, "text": text},
        "meta": "agent step",
    }


def _event_field(message: Any, key: str) -> Any:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)


def _component_payload_from_tool_response(message: Any) -> dict[str, Any]:
    if str(_event_field(message, "type") or "").strip() != "tool.response":
        return {}
    if (
        str(_event_field(message, "name") or "").strip()
        not in CHAT_COMPONENT_TOOL_NAMES
    ):
        return {}
    payload = _event_field(message, "payload")
    if not isinstance(payload, dict):
        return {}
    result = payload.get("result")
    if not isinstance(result, dict):
        return {}
    status = str(result["status"]).strip()
    if status == "error":
        error = str(result["error"]).strip()
        text_parts = [error]
        message_text = str(result.get("message") or "").strip()
        if message_text:
            text_parts.append(message_text)
        path = str(result.get("path") or "").strip()
        if path:
            text_parts.append(f"path: {path}")
        component_kind, component = normalize_component_payload(
            "Alert",
            {
                "title": lit("Component error"),
                "description": lit("\n".join(text_parts)),
                "variant": "destructive",
            },
        )
        return {
            "component_kind": component_kind,
            "components": [component],
        }
    if status != "ok":
        return {}
    component_kind = str(result.get("component_kind") or "").strip()
    components = result.get("components")
    if not component_kind or not isinstance(components, list) or not components:
        return {}
    return {
        "component_kind": component_kind,
        "components": components,
    }


def _persist_component_from_tool_response(
    module_sdk,
    conversation: Conversation,
    message: Message,
    event: Any,
) -> ChatComponent | None:
    payload = _component_payload_from_tool_response(event)
    if not payload:
        return None
    component_kind = str(payload["component_kind"])
    return module_sdk.database.add(
        ChatComponent(
            conversation_id=int(conversation.id),
            message_id=int(message.id),
            sequence=next_sequence(module_sdk, int(conversation.id)),
            component_kind=component_kind,
            payload={
                "kind": component_kind,
                "components": list(payload["components"]),
            },
        )
    )


@action("submit_message")
@permission_required(["chat.write"])
async def submit_message(ctx: dict[str, Any], session: dict, module_sdk):
    conversation_id = ctx.get("conversation_id") or None
    if not conversation_id:
        await _publish_toast(
            module_sdk,
            str(ctx["stream_id"]).strip(),
            level="error",
            message="conversation_id_required",
        )
        return module_sdk.effects.respond()
    effects, conversation = await _submit_thread_message(ctx, module_sdk)
    return effects


@action("start_thread")
@permission_required(["chat.write"])
async def start_thread(ctx: dict[str, Any], session: dict, module_sdk):
    stream_id = str(ctx["stream_id"]).strip()

    effects, conversation = await _submit_thread_message(ctx, module_sdk)
    thread_path = f"/chat/thread/{conversation.id}"
    return module_sdk.effects.respond(
        module_sdk.effects.navigate(thread_path, render=True)
    )


async def _submit_thread_message(ctx: dict[str, Any], module_sdk):
    stream_id = str(ctx["stream_id"]).strip()

    try:
        result = create_user_turn(module_sdk, ctx)
    except ValueError as exc:
        if str(exc) != "chat_message_empty":
            raise

        await _publish_toast(
            module_sdk,
            stream_id,
            level="warning",
            message=module_sdk.i18n.t("chat.toast.empty_message"),
        )
        return module_sdk.effects.respond()

    conversation = result["conversation"]
    message = result["message"]
    status_id = f"agent_status_{uuid4().hex}"
    request_id = uuid4().hex
    initial_status = _agent_status_row(
        status_id,
        title=module_sdk.i18n.t("chat.agent.status.running"),
        text=module_sdk.i18n.t("chat.agent.status.started"),
    )
    user_row = _message_record_with_attachments(message, result["attachments"])
    task_rows = [_message_record(row) for row in result["task_messages"]]

    await _publish_message_append(module_sdk, stream_id, user_row)
    for row in task_rows:
        await _publish_message_append(module_sdk, stream_id, row)
    await _publish_composer_request(module_sdk, stream_id, request_id)
    await module_sdk.effects.publish_property_update(
        stream_id,
        "chat_composer",
        "value",
        "",
    )

    response_effects = []
    await _publish_message_append(module_sdk, stream_id, initial_status)
    if result["created"]:
        conversation = await _generate_thread_title(module_sdk, conversation, message)

    async def on_step(row: dict[str, Any]) -> None:
        step_row = {**row, "id": status_id}
        await _publish_message_replace(module_sdk, stream_id, status_id, step_row)

    async def on_agent_message(event: Any) -> None:
        component = _persist_component_from_tool_response(
            module_sdk,
            conversation,
            message,
            event,
        )
        if component is None:
            return
        row = component_model_row(component)
        await _publish_message_append(module_sdk, stream_id, row)
        await _publish_messages_scroll_bottom(module_sdk, stream_id)

    assistant_temp_id = f"assistant_stream_{uuid4().hex}"
    assistant_stream_started = False
    assistant_stream_text = ""
    assistant_stream_reasoning = ""

    def _assistant_stream_row(
        row_id: str,
        text: str,
        reasoning: str = "",
        *,
        status: str = "streaming",
    ) -> dict[str, Any]:
        content = {"text": text}
        if reasoning:
            content["reasoning"] = reasoning
        return {
            "id": row_id,
            "role": "assistant",
            "kind": "text",
            "status": status,
            "content": content,
            "meta": module_sdk.i18n.t("chat.agent.status.running"),
        }

    async def on_stream_delta(text: str, reasoning: str = "") -> None:
        nonlocal assistant_stream_started, assistant_stream_text, assistant_stream_reasoning
        assistant_stream_text = text
        assistant_stream_reasoning = reasoning
        if not assistant_stream_started:
            assistant_stream_started = True
            await _publish_message_append(
                module_sdk,
                stream_id,
                _assistant_stream_row(assistant_temp_id, text, reasoning),
            )
            await _publish_messages_scroll_bottom(module_sdk, stream_id)
            return
        await _publish_message_replace(
            module_sdk,
            stream_id,
            assistant_temp_id,
            _assistant_stream_row(assistant_temp_id, text, reasoning),
        )

    try:
        assistant_message = await run_chat_orchestration(
            module_sdk,
            ctx,
            conversation,
            message,
            request_id=request_id,
            on_step=on_step,
            on_message=on_agent_message,
            on_stream_start=None,
            on_stream_delta=on_stream_delta,
        )
        if assistant_message is not None:
            assistant_row = _message_record(assistant_message)
            if assistant_stream_started:
                await _publish_message_replace(
                    module_sdk,
                    stream_id,
                    assistant_temp_id,
                    assistant_row,
                )
            else:
                await _publish_message_append(module_sdk, stream_id, assistant_row)

        await _publish_message_remove(module_sdk, stream_id, status_id)

        conversation = await _refresh_thread_summary(module_sdk, conversation)
        for message in _thread_list_update_messages(
            module_sdk,
            page=0,
            surface_id=_thread_list_surface_id(ctx),
            active_thread_id=conversation.id,
        ):
            await module_sdk.effects.publish_ui_message(stream_id, message)

    except asyncio.CancelledError:
        cancelled_status = _agent_status_row(
            status_id,
            title=module_sdk.i18n.t("chat.agent.status.failed"),
            text="request_cancelled",
            status="failed",
        )
        await _publish_message_replace(
            module_sdk,
            stream_id,
            status_id,
            cancelled_status,
        )

    except Exception as exc:
        raise exc
        failed_status = _agent_status_row(
            status_id,
            title=module_sdk.i18n.t("chat.agent.status.failed"),
            text=str(exc),
            status="failed",
        )
        if assistant_stream_started:
            await _publish_message_replace(
                module_sdk,
                stream_id,
                assistant_temp_id,
                _assistant_stream_row(
                    assistant_temp_id,
                    assistant_stream_text,
                    assistant_stream_reasoning,
                    status="failed",
                ),
            )
        await _publish_message_replace(module_sdk, stream_id, status_id, failed_status)
        await _publish_toast(
            module_sdk,
            stream_id,
            level="error",
            message=str(exc),
        )

    finally:
        await _publish_composer_request(module_sdk, stream_id, "")
    return module_sdk.effects.respond(*response_effects), conversation


@action("stop_generation")
@permission_required(["chat.write"])
async def stop_generation(ctx: dict[str, Any], session: dict, module_sdk):
    payload = ctx.get("chat_composer")
    request_id = payload.get("current_request")
    if not request_id:
        return module_sdk.effects.respond()
    module_sdk.ai.cancel_request(request_id)

    await _publish_composer_request(module_sdk, ctx.get("stream_id"), "")

    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update("chat_composer", "current_request", "")
    )


@action("open_thread")
@permission_required(["chat.view"])
async def open_thread(ctx: dict[str, Any], session: dict, module_sdk):
    thread_id = ctx.get("threadId") or ctx.get("item_id")
    if not thread_id:
        return module_sdk.effects.respond()
    return module_sdk.effects.respond(
        module_sdk.effects.navigate(f"/chat/thread/{thread_id}", render=True)
    )


@action("thread_page_prev")
@permission_required(["chat.view"])
async def thread_page_prev(ctx: dict[str, Any], session: dict, module_sdk):
    surface_id = _thread_list_surface_id(ctx)
    current_page = await _current_thread_list_page(
        ctx, module_sdk, surface_id=surface_id
    )
    active_thread_id = await _current_thread_list_active_id(
        ctx,
        module_sdk,
        surface_id=surface_id,
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            _thread_list_update_messages(
                module_sdk,
                page=max(0, current_page - 1),
                surface_id=surface_id,
                active_thread_id=active_thread_id,
            )
        )
    )


@action("thread_page_next")
@permission_required(["chat.view"])
async def thread_page_next(ctx: dict[str, Any], session: dict, module_sdk):
    surface_id = _thread_list_surface_id(ctx)
    current_page = await _current_thread_list_page(
        ctx, module_sdk, surface_id=surface_id
    )
    active_thread_id = await _current_thread_list_active_id(
        ctx,
        module_sdk,
        surface_id=surface_id,
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            _thread_list_update_messages(
                module_sdk,
                page=current_page + 1,
                surface_id=surface_id,
                active_thread_id=active_thread_id,
            )
        )
    )


@action("rename_thread")
@permission_required(["chat.write"])
async def rename_thread(ctx: dict[str, Any], session: dict, module_sdk):
    conversation_id = str(ctx.get("conversation_id") or "").strip()
    title = str(ctx.get("title") or "").strip()
    if not conversation_id or not title:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("chat.thread.rename.error.title"),
                    "text": module_sdk.i18n.t("chat.thread.rename.error.text"),
                    "variant": "destructive",
                },
            )
        )

    conversation = module_sdk.database.update(
        Conversation,
        conversation_id,
        title=title,
    )
    if conversation is None:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("chat.thread.rename.error.title"),
                    "text": module_sdk.i18n.t("chat.thread.not_found"),
                    "variant": "destructive",
                },
            )
        )

    surface_id = _thread_list_surface_id(ctx)
    current_page = await _current_thread_list_page(
        ctx, module_sdk, surface_id=surface_id
    )
    active_thread_id = await _current_thread_list_active_id(
        ctx,
        module_sdk,
        surface_id=surface_id,
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {"deleteSurface": {"surfaceId": "drawer"}},
                *_thread_list_update_messages(
                    module_sdk,
                    page=current_page,
                    surface_id=surface_id,
                    active_thread_id=active_thread_id,
                ),
            ]
        ),
        module_sdk.effects.notify(
            "toast",
            {
                "title": module_sdk.i18n.t("chat.thread.rename.toast.title"),
                "text": module_sdk.i18n.t("chat.thread.rename.toast.text"),
                "variant": "success",
            },
        ),
    )


def _delete_rows(module_sdk, model, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        module_sdk.database.delete(model, str(row["id"]))


@action("delete_thread")
@permission_required(["chat.write"])
async def delete_thread(ctx: dict[str, Any], session: dict, module_sdk):
    conversation_id = str(
        ctx.get("item_id") or ctx.get("conversation_id") or ""
    ).strip()
    if not conversation_id:
        return module_sdk.effects.respond()

    conversation = module_sdk.database.get(Conversation, conversation_id)
    if conversation is None:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("chat.thread.delete.error.title"),
                    "text": module_sdk.i18n.t("chat.thread.not_found"),
                    "variant": "destructive",
                },
            )
        )

    filters = {"conversation_id": int(conversation_id)}
    attachments = Attachment.all(filters=filters)["rows"]
    components = ChatComponent.all(filters=filters)["rows"]
    messages = Message.all(filters=filters)["rows"]

    module_sdk.knowledge.delete_by_metadata(
        {"conversation_id": conversation_id},
        force=True,
    )
    file_ids = [
        str(row.get("file_id") or "").strip()
        for row in attachments
        if str(row.get("file_id") or "").strip()
    ]
    for file_id in dict.fromkeys(file_ids):
        module_sdk.knowledge.delete_by_metadata({"file_id": file_id}, force=True)

    storage_paths = [
        str(row.get("storage_path") or "").strip()
        for row in attachments
        if str(row.get("storage_path") or "").strip()
    ]
    for storage_path in dict.fromkeys(storage_paths):
        module_sdk.media.delete(storage_path)

    _delete_rows(module_sdk, Attachment, attachments)
    _delete_rows(module_sdk, ChatComponent, components)
    _delete_rows(module_sdk, Message, messages)
    module_sdk.database.delete(Conversation, conversation_id)

    surface_id = _thread_list_surface_id(ctx)
    current_page = await _current_thread_list_page(
        ctx, module_sdk, surface_id=surface_id
    )
    active_thread_id = await _current_thread_list_active_id(
        ctx,
        module_sdk,
        surface_id=surface_id,
    )
    messages_payload = _thread_list_update_messages(
        module_sdk,
        page=current_page,
        surface_id=surface_id,
        active_thread_id=active_thread_id,
    )
    effects = [
        module_sdk.effects.ui_messages(messages_payload),
        module_sdk.effects.notify(
            "toast",
            {
                "title": module_sdk.i18n.t("chat.thread.delete.toast.title"),
                "text": module_sdk.i18n.t("chat.thread.delete.toast.text"),
                "variant": "success",
            },
        ),
    ]
    if active_thread_id == conversation_id:
        effects.append(module_sdk.effects.navigate("/chat", render=True))
    return module_sdk.effects.respond(*effects)


@action("load_older_messages")
@permission_required(["chat.view"])
async def load_older_messages(ctx: dict[str, Any], session: dict, module_sdk):
    conversation_id = int(ctx.get("conversation_id") or None)
    if not conversation_id:
        return module_sdk.effects.respond()

    stream_id = ctx.get("stream_id")
    before_sequence = 0

    current = await module_sdk.effects.ask_current_store_value(
        stream_id,
        CHAT_OLDEST_SEQUENCE_STORE,
        "page",
    )
    before_sequence = int(current or 0)

    if before_sequence <= 0:
        before_sequence = int(ctx.get("before_sequence") or 0)
    if before_sequence <= 0:
        return module_sdk.effects.respond()
    rows = thread_messages_before(
        module_sdk,
        conversation_id,
        before_sequence,
        page_size=THREAD_MESSAGE_PAGE_SIZE,
    )
    if not rows:
        return module_sdk.effects.respond()
    next_oldest_sequence = visible_oldest_sequence(module_sdk, rows)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                _message_prepend(module_sdk, rows),
                _state_set(
                    module_sdk, CHAT_OLDEST_SEQUENCE_STORE, next_oldest_sequence
                ),
            ]
        )
    )


@action("new_thread")
@permission_required(["chat.write"])
async def new_thread(ctx: dict[str, Any], session: dict, module_sdk):
    return module_sdk.effects.respond(module_sdk.effects.navigate("/chat", render=True))
