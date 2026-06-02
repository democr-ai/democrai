from __future__ import annotations

from types import SimpleNamespace

import pytest

from democrai.core.application.ai.security.context.budget import tool_result_budget_chars
from modules.chat.tools import attachments as attachment_tools
from modules.chat.tools import retrieval as retrieval_tools
from modules.chat.utils.actions import orchestration as orchestration_tools


def test_list_attachments_returns_document_view(monkeypatch):
    monkeypatch.setattr(
        attachment_tools.Attachment,
        "list",
        lambda **_kwargs: {
            "rows": [
                {
                    "id": 1,
                    "name": "notes.pdf",
                    "mime_type": "application/pdf",
                    "storage_path": "media/chat/notes.pdf",
                    "file_id": "file-1",
                    "extraction_request_id": "req-1",
                    "metadata_json": {},
                },
                {
                    "id": 2,
                    "name": "photo.png",
                    "mime_type": "image/png",
                    "storage_path": "media/chat/photo.png",
                    "file_id": "file-2",
                    "extraction_request_id": "req-2",
                    "metadata_json": {},
                },
            ]
        },
    )
    sdk = SimpleNamespace(
        knowledge=SimpleNamespace(
            list_extraction_statuses=lambda _request_ids: {"items": []}
        )
    )

    result = attachment_tools.list_attachments(
        sdk=sdk,
        context={"conversation_id": 42},
    )

    assert result["status"] == "ok"
    assert [item["name"] for item in result["items"]] == ["notes.pdf", "photo.png"]
    assert [item["name"] for item in result["documents"]] == ["notes.pdf"]


def test_get_document_markdown_returns_structured_error(monkeypatch):
    monkeypatch.setattr(
        attachment_tools.Attachment,
        "list",
        lambda **_kwargs: {
            "rows": [
                {
                    "id": 1,
                    "conversation_id": 42,
                    "extraction_request_id": "req-1",
                }
            ]
        },
    )
    sdk = SimpleNamespace(
        knowledge=SimpleNamespace(
            get_extracted_document=lambda _request_id: (
                (_ for _ in ()).throw(
                    RuntimeError("knowledge_extraction_request_not_completed")
                )
            )
        )
    )

    result = attachment_tools.get_document_markdown(
        extraction_request_id="req-1",
        sdk=sdk,
        context={"conversation_id": 42},
    )

    assert result == {
        "status": "error",
        "error": "knowledge_extraction_request_not_completed",
        "request_id": "req-1",
    }


def test_get_document_markdown_uses_context_budget(monkeypatch):
    monkeypatch.setattr(
        attachment_tools.Attachment,
        "list",
        lambda **_kwargs: {
            "rows": [
                {
                    "id": 1,
                    "conversation_id": 42,
                    "extraction_request_id": "req-1",
                }
            ]
        },
    )
    sdk = SimpleNamespace(
        knowledge=SimpleNamespace(
            get_extracted_document=lambda _request_id: {
                "title": "notes.pdf",
                "mime_type": "application/pdf",
                "chunks_count": 1,
                "markdown_content": "abcdef",
            }
        )
    )

    result = attachment_tools.get_document_markdown(
        extraction_request_id="req-1",
        sdk=sdk,
        context={"conversation_id": 42, "tool_result_budget_chars": 4},
    )

    assert result["markdown"] == "abcd"
    assert result["truncated"] is True
    assert result["original_chars"] == 6
    assert result["returned_chars"] == 4
    assert result["budget_chars"] == 4


def test_split_markdown_sections_prefers_structure_without_losing_content():
    markdown = (
        "# One\n"
        + ("alpha " * 80)
        + "\n\n# Two\n"
        + ("beta " * 80)
        + "\n\n# Three\n"
        + ("gamma " * 80)
    )

    sections = attachment_tools._split_markdown_sections(markdown, 500)

    assert len(sections) > 1
    joined = "\n".join(sections)
    assert joined.count("alpha") == markdown.count("alpha")
    assert joined.count("beta") == markdown.count("beta")
    assert joined.count("gamma") == markdown.count("gamma")
    assert sections[0].startswith("# One")
    assert any(section.startswith("# Two") for section in sections)


def test_read_document_index_includes_document_summary(monkeypatch):
    monkeypatch.setattr(
        attachment_tools.Attachment,
        "list",
        lambda **_kwargs: {
            "rows": [
                {
                    "id": 1,
                    "conversation_id": 42,
                    "extraction_request_id": "req-1",
                }
            ]
        },
    )
    sdk = SimpleNamespace(
        knowledge=SimpleNamespace(
            read_document_blocks=lambda **_kwargs: {
                "request_id": "req-1",
                "mode": "index",
                "kind": "chunk",
                "blocks": [],
            },
            list_items_for_summary=lambda **_kwargs: [
                {"id": "doc-1", "summary": "document map", "fresh": True}
            ],
        )
    )

    result = attachment_tools.read_document(
        extraction_request_id="req-1",
        sdk=sdk,
        context={"conversation_id": 42},
    )

    assert result["status"] == "ok"
    assert result["document_summary"] == "document map"


@pytest.mark.asyncio
async def test_extract_full_summary_uses_document_not_chunks(monkeypatch):
    monkeypatch.setattr(
        attachment_tools.Attachment,
        "list",
        lambda **_kwargs: {
            "rows": [
                {
                    "id": 1,
                    "conversation_id": 42,
                    "extraction_request_id": "req-1",
                }
            ]
        },
    )

    markdown = "\n\n".join(
        f"# Section {index}\n" + (f"content {index} " * 120)
        for index in range(1, 7)
    )

    class Provider:
        def __init__(self):
            self.calls = []

        async def generate_completion(self, *, messages, options):
            self.calls.append({"messages": messages, "options": options})
            system = str(messages[0]["content"])
            if "large section of a document" in system:
                return SimpleNamespace(content=f"summary {len(self.calls)}")
            return SimpleNamespace(content="final document map")

    provider = Provider()
    summary_calls = []
    stored = []

    def list_items_for_summary(**kwargs):
        summary_calls.append(kwargs)
        if kwargs["item_type"] == "chunk":
            raise AssertionError("chunk summaries must not be used")
        return [{"id": "doc-1", "summary": "", "fresh": False}]

    async def get_provider_by_model_registry_id(_model_id):
        return {"status": "ok", "provider": provider}

    sdk = SimpleNamespace(
        knowledge=SimpleNamespace(
            list_items_for_summary=list_items_for_summary,
            get_extracted_document=lambda _request_id: {
                "markdown_content": markdown,
                "chunks_count": 48,
            },
            store_item_summary=lambda **kwargs: stored.append(kwargs) or True,
        ),
        ai=SimpleNamespace(
            get_provider_by_model_registry_id=get_provider_by_model_registry_id
        ),
        system=SimpleNamespace(log=lambda *_args, **_kwargs: None),
    )

    result = await attachment_tools.extract_full_summary(
        extraction_request_id="req-1",
        sdk=sdk,
        context={
            "conversation_id": 42,
            "model_registry_id": 7,
            "tool_result_budget_chars": 2400,
        },
    )

    assert result["status"] == "ok"
    assert result["summary"] == "final document map"
    assert result["sections_total"] < 48
    assert result["sections_summarized"] == result["sections_total"]
    assert stored == [{"item_id": "doc-1", "summary": "final document map"}]
    assert all(call["item_type"] == "document" for call in summary_calls)
    assert len(provider.calls) == result["sections_total"] + 1


@pytest.mark.asyncio
async def test_extract_full_summary_returns_fresh_document_cache(monkeypatch):
    monkeypatch.setattr(
        attachment_tools.Attachment,
        "list",
        lambda **_kwargs: {
            "rows": [
                {
                    "id": 1,
                    "conversation_id": 42,
                    "extraction_request_id": "req-1",
                }
            ]
        },
    )
    sdk = SimpleNamespace(
        knowledge=SimpleNamespace(
            list_items_for_summary=lambda **_kwargs: [
                {"id": "doc-1", "summary": "cached map", "fresh": True}
            ],
        ),
    )

    result = await attachment_tools.extract_full_summary(
        extraction_request_id="req-1",
        refresh=True,
        sdk=sdk,
        context={"conversation_id": 42},
    )

    assert result["status"] == "ok"
    assert result["cached"] is True
    assert result["summary"] == "cached map"
    assert result["sections_summarized"] == 0


def test_build_provider_messages_lists_attachments_and_directs_only_last_user(
    monkeypatch,
):
    monkeypatch.setattr(
        orchestration_tools.Message,
        "count",
        lambda **_kwargs: 2,
    )
    monkeypatch.setattr(
        orchestration_tools.Message,
        "list",
        lambda **_kwargs: {
            "rows": [
                {
                    "id": 11,
                    "role": "user",
                    "kind": "text",
                    "sequence": 1,
                    "content": {"text": "old"},
                },
                {
                    "id": 12,
                    "role": "assistant",
                    "kind": "text",
                    "sequence": 2,
                    "content": {"text": "ok"},
                },
                {
                    "id": 13,
                    "role": "user",
                    "kind": "text",
                    "sequence": 3,
                    "content": {"text": "new"},
                },
            ]
        },
    )
    monkeypatch.setattr(
        orchestration_tools.Attachment,
        "list",
        lambda **_kwargs: {
            "rows": [
                {
                    "id": 1,
                    "conversation_id": 42,
                    "message_id": 11,
                    "name": "old.png",
                    "mime_type": "image/png",
                    "storage_path": "/old.png",
                    "extraction_request_id": "req-old",
                },
                {
                    "id": 2,
                    "conversation_id": 42,
                    "message_id": 13,
                    "name": "new.png",
                    "mime_type": "image/png",
                    "storage_path": "/new.png",
                    "extraction_request_id": "",
                },
                {
                    "id": 3,
                    "conversation_id": 42,
                    "message_id": 13,
                    "name": "doc.pdf",
                    "mime_type": "application/pdf",
                    "storage_path": "/doc.pdf",
                    "extraction_request_id": "req-doc",
                },
            ]
        },
    )
    sdk = SimpleNamespace(
        knowledge=SimpleNamespace(
            list_extraction_statuses=lambda request_ids: {
                "items": [
                    {"request_id": "req-old", "extraction_status": "completed"},
                    {"request_id": "req-doc", "extraction_status": "pending"},
                ]
            }
        )
    )

    messages = orchestration_tools.build_provider_messages(
        sdk,
        SimpleNamespace(id=42, summary=""),
    )

    system_text = messages[0]["content"]
    assert "Current uploaded attachments:" in system_text
    assert "name=old.png" in system_text
    assert "mime_type=image/png" in system_text
    assert "extraction_status=completed" in system_text
    assert "name=new.png" in system_text
    assert "extraction_status=not_requested" in system_text
    assert "name=doc.pdf" in system_text
    assert "extraction_status=pending" in system_text
    old_message = next(item for item in messages if item["role"] == "user")
    assert old_message["content"] == "old"
    last_user_message = messages[-1]
    assert isinstance(last_user_message["content"], list)
    assert [part.get("storage_path") for part in last_user_message["content"][1:]] == [
        "/new.png"
    ]


def test_tool_result_budget_scales_with_model_context():
    assert tool_result_budget_chars(config={"context_length": 198000}) > 12000
    assert tool_result_budget_chars() <= 12000


@pytest.mark.asyncio
async def test_search_documents_falls_back_to_extracted_items_when_retrieval_is_empty(
    monkeypatch,
):
    monkeypatch.setattr(
        retrieval_tools.Attachment,
        "list",
        lambda **_kwargs: {"rows": [{"extraction_request_id": "req-1"}]},
    )
    calls = []

    async def _retrieve(**kwargs):
        calls.append(("retrieve", kwargs))
        return SimpleNamespace(matches=[])

    def _search_extracted_items(**kwargs):
        calls.append(("search_extracted_items", kwargs))
        return {"matches": [{"title": "notes.pdf", "content": "needle"}]}

    sdk = SimpleNamespace(
        knowledge=SimpleNamespace(
            get_runtime_config=lambda: {"enabled": True},
            retrieve=_retrieve,
            search_extracted_items=_search_extracted_items,
        )
    )

    result = await retrieval_tools.search_documents(
        "needle",
        sdk=sdk,
        context={"conversation_id": 42},
    )

    assert result["status"] == "ok"
    assert result["source"] == "extracted_items"
    assert result["matches"] == [{"title": "notes.pdf", "content": "needle"}]
    assert calls[0][0] == "retrieve"
    assert calls[1] == (
        "search_extracted_items",
        {
            "query_text": "needle",
            "limit": 8,
            "extraction_request_ids": ["req-1"],
        },
    )
