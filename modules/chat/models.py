from __future__ import annotations

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from democrai.sdk.database import get_module_base


Base = get_module_base("chat")


class Conversation(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_until_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at = mapped_column(DateTime, nullable=True)

    @classmethod
    def filters_model(cls) -> list[dict]:
        return [
            {"key": "id", "column": "id", "operator": "eq"},
            {"key": "title", "column": "title", "operator": "ilike"},
        ]


class Message(Base):
    __audit_compact_fields__ = {"content"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    @classmethod
    def filters_model(cls) -> list[dict]:
        return [
            {"key": "id", "column": "id", "operator": "eq"},
            {"key": "conversation_id", "column": "conversation_id", "operator": "eq"},
            {"key": "role", "column": "role", "operator": "eq"},
            {"key": "kind", "column": "kind", "operator": "eq"},
            {"key": "status", "column": "status", "operator": "eq"},
            {"key": "before_sequence", "column": "sequence", "operator": "lt"},
            {"key": "after_sequence", "column": "sequence", "operator": "gt"},
            {
                "key": "content_query",
                "column": "content",
                "operator": "ilike",
                "cast": "string",
                "escape": "\\",
            },
        ]


class Attachment(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    extraction_request_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    @classmethod
    def filters_model(cls) -> list[dict]:
        return [
            {"key": "id", "column": "id", "operator": "eq"},
            {"key": "conversation_id", "column": "conversation_id", "operator": "eq"},
            {"key": "message_id", "column": "message_id", "operator": "eq"},
            {"key": "message_ids", "column": "message_id", "operator": "in"},
            {"key": "extraction_request_id", "column": "extraction_request_id", "operator": "eq"},
        ]


class ChatComponent(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    component_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    @classmethod
    def filters_model(cls) -> list[dict]:
        return [
            {"key": "id", "column": "id", "operator": "eq"},
            {"key": "conversation_id", "column": "conversation_id", "operator": "eq"},
            {"key": "message_id", "column": "message_id", "operator": "eq"},
            {"key": "component_kind", "column": "component_kind", "operator": "eq"},
            {"key": "before_sequence", "column": "sequence", "operator": "lt"},
        ]
