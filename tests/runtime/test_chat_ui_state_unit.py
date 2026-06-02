from __future__ import annotations

from datetime import datetime
import json
from types import SimpleNamespace

import pytest

from modules.chat.utils.ui import state


def test_recent_threads_queries_messages_by_real_conversation_id(monkeypatch):
    message_calls = []

    monkeypatch.setattr(
        state.Conversation,
        "list",
        lambda **_kwargs: {
            "rows": [{"id": 42, "title": "Thread", "updated_at": None}]
        },
    )

    def _message_list(**kwargs):
        message_calls.append(kwargs)
        return {"rows": []}

    monkeypatch.setattr(state.Message, "list", _message_list)
    monkeypatch.setattr(
        state,
        "thread_row",
        lambda row, message: {"id": row["id"], "message": message},
    )

    rows = state.recent_threads(SimpleNamespace())

    assert rows == [{"id": 42, "message": None, "active": False}]
    assert message_calls[0]["filters"] == {"conversation_id": 42}


def test_thread_messages_uses_real_row_ids_for_attachments(monkeypatch):
    message_calls = []
    attachment_calls = []

    def _message_list(**kwargs):
        message_calls.append(kwargs)
        return {
            "rows": [
                {
                    "id": 7,
                    "role": "user",
                    "kind": "text",
                    "status": "completed",
                    "sequence": 3,
                    "content": {"text": "hello"},
                    "created_at": datetime(2026, 5, 29, 11, 2),
                    "updated_at": datetime(2026, 5, 29, 11, 3),
                }
            ]
        }

    def _component_list(**_kwargs):
        return {"rows": []}

    def _attachment_all(**kwargs):
        attachment_calls.append(kwargs)
        return {
            "rows": [
                {
                    "id": 9,
                    "message_id": 7,
                    "created_at": datetime(2026, 5, 29, 11, 4),
                    "updated_at": datetime(2026, 5, 29, 11, 5),
                }
            ]
        }

    monkeypatch.setattr(state.Message, "list", _message_list)
    monkeypatch.setattr(state.ChatComponent, "list", _component_list)
    monkeypatch.setattr(state.Attachment, "all", _attachment_all)
    rows = state.thread_messages(SimpleNamespace(), 42)

    assert message_calls[0]["filters"] == {"conversation_id": 42}
    assert attachment_calls[0]["filters"] == {
        "conversation_id": 42,
        "message_ids": [7],
    }
    assert rows == [
        {
            "id": 7,
            "role": "user",
            "kind": "text",
            "status": "completed",
            "sequence": 3,
            "created_at": "2026-05-29T11:02:00",
            "updated_at": "2026-05-29T11:03:00",
            "content": {
                "text": "hello",
                "attachments": [
                    {
                        "id": 9,
                        "message_id": 7,
                        "created_at": "2026-05-29T11:04:00",
                        "updated_at": "2026-05-29T11:05:00",
                    }
                ],
            },
        }
    ]
    json.dumps(rows)


def test_stt_configured_uses_model_registry_without_provider_resolution():
    model_calls: list[dict] = []

    sdk = SimpleNamespace(
        models=SimpleNamespace(
            model_registry=SimpleNamespace(
                list=lambda **kwargs: model_calls.append(kwargs)
                or {"rows": [{"capabilities": ["stt"]}]}
            )
        )
    )

    assert state.stt_configured(sdk) is True
    assert model_calls == [
        {"page": 0, "page_size": 100, "filters": {"capabilies": "stt", "status": "active"}}
    ]
