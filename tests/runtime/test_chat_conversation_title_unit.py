from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.chat.actions import conversation as conversation_actions


class _Effects:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    def navigate(self, path: str, *, render: bool = False):
        return {"effect": "navigate", "path": path, "render": render}

    def notify(self, name: str, payload: dict):
        return {"effect": "notify", "name": name, "payload": payload}

    def ui_messages(self, messages: list[dict]):
        return {"effect": "ui_messages", "messages": messages}

    def respond(self, *effects):
        return {"effects": list(effects)}

    async def publish_ui_message(self, stream_id: str, message: dict):
        self.published.append((stream_id, message))

    async def publish_property_update(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value,
    ):
        self.published.append(
            (
                stream_id,
                {
                    "propertyUpdate": {
                        "componentId": component_id,
                        "propertyName": property_name,
                        "value": value,
                    }
                },
            )
        )

    async def publish_collection_append(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value,
    ):
        self.published.append(
            (
                stream_id,
                {
                    "collectionAppend": {
                        "componentId": component_id,
                        "propertyName": property_name,
                        "value": value,
                    }
                },
            )
        )

    async def publish_collection_replace(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value,
    ):
        self.published.append(
            (
                stream_id,
                {
                    "collectionReplace": {
                        "componentId": component_id,
                        "propertyName": property_name,
                        "value": value,
                    }
                },
            )
        )

    async def publish_collection_remove(
        self,
        stream_id: str,
        component_id: str,
        property_name: str,
        value,
    ):
        self.published.append(
            (
                stream_id,
                {
                    "collectionRemove": {
                        "componentId": component_id,
                        "propertyName": property_name,
                        "value": value,
                    }
                },
            )
        )


def _sdk() -> SimpleNamespace:
    effects = _Effects()
    return SimpleNamespace(
        effects=effects,
        i18n=SimpleNamespace(
            t=lambda key, **_kwargs: "New chat"
            if key == "chat.thread.untitled"
            else key
        ),
    )


@pytest.mark.asyncio
async def test_start_thread_generates_title_for_new_conversation(monkeypatch):
    calls: list[str] = []
    conversation = SimpleNamespace(id=42, title="New chat")
    message = SimpleNamespace(id=7, content={"text": "hello"})

    monkeypatch.setattr(
        conversation_actions,
        "create_user_turn",
        lambda _sdk, _ctx: {
            "conversation": conversation,
            "message": message,
            "attachments": [],
            "task_messages": [],
            "created": True,
        },
    )

    async def _generate_title(_sdk, conv, msg):
        calls.append(f"{conv.id}:{msg.id}")
        conv.title = "Generated title"
        return conv

    monkeypatch.setattr(conversation_actions, "_generate_thread_title", _generate_title)

    async def _orchestrate(*_args, **_kwargs):
        return None

    monkeypatch.setattr(conversation_actions, "run_chat_orchestration", _orchestrate)
    monkeypatch.setattr(
        conversation_actions,
        "_message_record_with_attachments",
        lambda msg, _attachments: {"id": msg.id},
    )
    monkeypatch.setattr(
        conversation_actions,
        "_refresh_thread_summary",
        lambda _sdk, conv: _async_value(conv),
    )
    monkeypatch.setattr(
        conversation_actions,
        "_thread_list_update_messages",
        lambda *_args, **_kwargs: [],
    )

    result = await conversation_actions.start_thread(
        {"stream_id": "stream-1"},
        {},
        _sdk(),
    )

    assert calls == ["42:7"]
    assert result == {
        "effects": [{"effect": "navigate", "path": "/chat/thread/42", "render": True}]
    }


@pytest.mark.asyncio
async def test_start_thread_does_not_generate_title_for_existing_conversation(
    monkeypatch,
):
    calls: list[str] = []
    conversation = SimpleNamespace(id=42, title="Existing title")
    message = SimpleNamespace(id=8, content={"text": "hello again"})

    monkeypatch.setattr(
        conversation_actions,
        "create_user_turn",
        lambda _sdk, _ctx: {
            "conversation": conversation,
            "message": message,
            "attachments": [],
            "task_messages": [],
            "created": False,
        },
    )

    async def _generate_title(*_args, **_kwargs):
        calls.append("called")
        return conversation

    monkeypatch.setattr(conversation_actions, "_generate_thread_title", _generate_title)

    async def _orchestrate(*_args, **_kwargs):
        return None

    monkeypatch.setattr(conversation_actions, "run_chat_orchestration", _orchestrate)
    monkeypatch.setattr(
        conversation_actions,
        "_message_record_with_attachments",
        lambda msg, _attachments: {"id": msg.id},
    )
    monkeypatch.setattr(
        conversation_actions,
        "_refresh_thread_summary",
        lambda _sdk, conv: _async_value(conv),
    )
    monkeypatch.setattr(
        conversation_actions,
        "_thread_list_update_messages",
        lambda *_args, **_kwargs: [],
    )

    await conversation_actions.start_thread({"stream_id": "stream-1"}, {}, _sdk())

    assert calls == []


@pytest.mark.asyncio
async def test_generate_thread_title_uses_first_ten_user_text_characters():
    conversation = SimpleNamespace(id=42, title="New chat")
    message = SimpleNamespace(id=7, content={"text": "hello wonderful world"})
    updates: list[dict] = []
    sdk = _sdk()
    sdk.database = SimpleNamespace(
        update=lambda *_args, **kwargs: updates.append(kwargs) or conversation
    )

    result = await conversation_actions._generate_thread_title(
        sdk, conversation, message
    )

    assert result is conversation
    assert updates == [{"title": "hello wond"}]


@pytest.mark.asyncio
async def test_delete_thread_deletes_knowledge_by_conversation_metadata(monkeypatch):
    deleted_rows: list[tuple[type, str]] = []
    knowledge_calls: list[dict] = []
    media_deleted: list[str] = []
    sdk = _sdk()
    sdk.database = SimpleNamespace(
        get=lambda model, row_id: SimpleNamespace(id=int(row_id))
        if model is conversation_actions.Conversation
        else None,
        delete=lambda model, row_id: deleted_rows.append((model, row_id)) or True,
    )
    sdk.knowledge = SimpleNamespace(
        delete_by_metadata=lambda filters, **kwargs: knowledge_calls.append(
            {"filters": filters, **kwargs}
        )
        or {"deleted_items": ()}
    )
    sdk.media = SimpleNamespace(delete=lambda path: media_deleted.append(path))

    monkeypatch.setattr(
        conversation_actions.Attachment,
        "all",
        lambda filters: {
            "rows": [
                {
                    "id": 1,
                    "conversation_id": filters["conversation_id"],
                    "storage_path": "media/chat/a.txt",
                    "file_id": "file-1",
                }
            ]
        },
    )
    monkeypatch.setattr(
        conversation_actions.ChatComponent,
        "all",
        lambda filters: {"rows": [{"id": 2, "conversation_id": filters["conversation_id"]}]},
    )
    monkeypatch.setattr(
        conversation_actions.Message,
        "all",
        lambda filters: {"rows": [{"id": 3, "conversation_id": filters["conversation_id"]}]},
    )
    monkeypatch.setattr(
        conversation_actions,
        "_current_thread_list_page",
        lambda *_args, **_kwargs: _async_value(0),
    )
    monkeypatch.setattr(
        conversation_actions,
        "_current_thread_list_active_id",
        lambda *_args, **_kwargs: _async_value(""),
    )
    monkeypatch.setattr(
        conversation_actions,
        "_thread_list_update_messages",
        lambda *_args, **_kwargs: [{"replace": "threads"}],
    )

    result = await conversation_actions.delete_thread(
        {"conversation_id": "42"},
        {},
        sdk,
    )

    assert knowledge_calls == [
        {"filters": {"conversation_id": "42"}, "force": True},
        {"filters": {"file_id": "file-1"}, "force": True},
    ]
    assert media_deleted == ["media/chat/a.txt"]
    assert deleted_rows == [
        (conversation_actions.Attachment, "1"),
        (conversation_actions.ChatComponent, "2"),
        (conversation_actions.Message, "3"),
        (conversation_actions.Conversation, "42"),
    ]
    assert result["effects"][0]["messages"] == [{"replace": "threads"}]


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_start_thread_publishes_navigation_before_orchestration(monkeypatch):
    events: list[str] = []
    conversation = SimpleNamespace(id=42, title="New chat")
    message = SimpleNamespace(id=7, content={"text": "hello"})
    sdk = _sdk()

    monkeypatch.setattr(
        conversation_actions,
        "create_user_turn",
        lambda _sdk, _ctx: {
            "conversation": conversation,
            "message": message,
            "attachments": [],
            "task_messages": [],
            "created": True,
        },
    )

    async def _generate_title(_sdk, conv, _msg):
        events.append("title")
        return conv

    monkeypatch.setattr(conversation_actions, "_generate_thread_title", _generate_title)

    async def _orchestrate(*_args, **_kwargs):
        events.append("orchestrate")
        return None

    monkeypatch.setattr(conversation_actions, "run_chat_orchestration", _orchestrate)
    monkeypatch.setattr(
        conversation_actions,
        "_message_record_with_attachments",
        lambda msg, _attachments: {"id": msg.id},
    )
    monkeypatch.setattr(
        conversation_actions,
        "_refresh_thread_summary",
        lambda _sdk, conv: _async_value(conv),
    )
    monkeypatch.setattr(
        conversation_actions,
        "_thread_list_update_messages",
        lambda *_args, **_kwargs: [],
    )

    result = await conversation_actions.start_thread(
        {"stream_id": "stream-1"},
        session := {},
        sdk,
    )

    assert result == {
        "effects": [{"effect": "navigate", "path": "/chat/thread/42", "render": True}]
    }
    assert events == [
        "title",
        "orchestrate",
    ]
    assert sdk.effects.published[0] == (
        "stream-1",
        {
            "collectionAppend": {
                "componentId": "chat_message_list",
                "propertyName": "messages",
                "value": {"id": 7},
            }
        },
    )


@pytest.mark.asyncio
async def test_start_thread_requires_stream_id_from_context(monkeypatch):
    conversation = SimpleNamespace(id=42, title="New chat")
    message = SimpleNamespace(id=7, content={"text": "hello"})

    monkeypatch.setattr(
        conversation_actions,
        "create_user_turn",
        lambda _sdk, _ctx: {
            "conversation": conversation,
            "message": message,
            "attachments": [],
            "task_messages": [],
            "created": False,
        },
    )

    async def _orchestrate(*_args, **_kwargs):
        return None

    monkeypatch.setattr(conversation_actions, "run_chat_orchestration", _orchestrate)

    with pytest.raises(KeyError, match="stream_id"):
        await conversation_actions.start_thread({}, {}, _sdk())
