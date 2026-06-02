from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from modules.chat.models import Conversation
from modules.chat.utils.actions import orchestration


class _Provider:
    async def generate_stream(self, **_kwargs):
        yield {"delta": "Intro "}
        yield {"delta": "<untrusted-content"}
        yield {"delta": ' source="model_output" intent="model_response">\n'}
        yield {"delta": "visible"}
        yield {"delta": "\n</untrusted-content> outro"}


class _Database:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, row: Any) -> Any:
        row.id = len(self.added) + 100
        self.added.append(row)
        return row

    def update(self, _model: Any, _row_id: str, **_values: Any) -> None:
        return None


class _SDK:
    def __init__(self) -> None:
        self.database = _Database()
        self.knowledge = SimpleNamespace(get_runtime_config=lambda: {"enabled": False})
        self.ai = SimpleNamespace(
            get_provider_for_objective=self._get_provider_for_objective
        )

    async def _get_provider_for_objective(self, *_args, **_kwargs):
        return {"status": "ok", "provider": _Provider()}


@pytest.mark.asyncio
async def test_chat_stream_hides_untrusted_content_tags_before_final_cleanup(monkeypatch):
    user_row = {
        "id": 1,
        "conversation_id": 10,
        "role": "user",
        "kind": "text",
        "status": "completed",
        "sequence": 1,
        "content": {"text": "Say hello."},
    }

    monkeypatch.setattr(orchestration.Message, "count", lambda **_kwargs: 1)
    monkeypatch.setattr(
        orchestration.Message,
        "list",
        lambda **_kwargs: {"rows": [user_row]},
    )
    monkeypatch.setattr(
        orchestration.Attachment,
        "list",
        lambda **_kwargs: {"rows": []},
    )
    monkeypatch.setattr(
        "modules.chat.utils.actions.messages.ChatComponent.list",
        lambda **_kwargs: {"rows": []},
    )

    sdk = _SDK()
    deltas: list[str] = []

    async def _on_stream_delta(text: str, _reasoning: str = "") -> None:
        deltas.append(text)

    message = await orchestration.run_chat_orchestration(
        sdk,
        {"text": "Say hello."},
        Conversation(id=10, title="", summary="", summary_until_sequence=0),
        SimpleNamespace(id=1),
        on_stream_delta=_on_stream_delta,
    )

    assert deltas == [
        "Intro ",
        "Intro ",
        "Intro \n",
        "Intro \nvisible",
        "Intro \nvisible\n outro",
    ]
    assert all("<untrusted-content" not in delta for delta in deltas)
    assert message is not None
    assert message.content["text"] == "Intro \nvisible\n outro"
