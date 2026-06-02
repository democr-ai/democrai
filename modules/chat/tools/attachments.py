from __future__ import annotations

import re
from typing import Any

from democrai.sdk.client import active_sdk
from democrai.sdk.decorators import tool

from modules.chat.models import Attachment


def _sdk(sdk):
    return sdk if sdk is not None else active_sdk


def _conversation_id(context: dict[str, Any] | None) -> int:
    return int((context or {}).get("conversation_id") or 0)


def _status_map(sdk, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    request_ids = [
        row["extraction_request_id"] for row in rows if row["extraction_request_id"]
    ]
    if not request_ids:
        return {}
    result = sdk.knowledge.list_extraction_statuses(request_ids)
    return {
        str(item.get("request_id") or ""): dict(item)
        for item in list(result.get("items") or [])
        if isinstance(item, dict)
    }


def _is_document_attachment(item: dict[str, Any]) -> bool:
    mime_type = item["mime_type"].lower()
    if mime_type.startswith(("image/", "audio/", "video/")):
        return False
    return bool(item["extraction_request_id"])


@tool(
    "list-attachments",
    title="List chat attachments",
    description="List attachments for the current chat thread with extraction status.",
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)
def list_attachments(
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_sdk = _sdk(sdk)
    resolved_id = _conversation_id(context)
    if resolved_id <= 0:
        return {"status": "error", "error": "conversation_id_required"}
    result = Attachment.list(
        filters={"conversation_id": resolved_id},
        sort={"field": "id", "direction": "asc"},
        page=0,
        page_size=200,
    )
    rows = result["rows"]
    statuses = _status_map(module_sdk, rows)
    items = []
    for row in rows:
        item = {**row}
        for key in ("created_at", "updated_at"):
            value = item.get(key)
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        item["extraction"] = statuses.get(item["extraction_request_id"], {})
        items.append(item)
    return {
        "status": "ok",
        "conversation_id": resolved_id,
        "items": items,
        "documents": [item for item in items if _is_document_attachment(item)],
    }


@tool(
    "get-document-markdown",
    title="Get extracted markdown",
    description="Return the complete markdown extracted from one uploaded document.",
    input_schema={
        "type": "object",
        "properties": {
            "attachment_id": {"type": "integer"},
            "extraction_request_id": {"type": "string"},
        },
    },
)
def get_document_markdown(
    attachment_id: int | str = 0,
    extraction_request_id: str = "",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_sdk = _sdk(sdk)
    conversation_id = _conversation_id(context)
    if conversation_id <= 0:
        return {"status": "error", "error": "conversation_id_required"}
    request_id = str(extraction_request_id or "").strip()
    attachment = None
    if not request_id and int(attachment_id or 0) > 0:
        attachment = module_sdk.database.get(Attachment, int(attachment_id))
        if attachment is not None:
            request_id = attachment.extraction_request_id
    if not request_id:
        return {"status": "error", "error": "extraction_request_id_required"}
    if attachment is None:
        result = Attachment.list(
            filters={
                "conversation_id": conversation_id,
                "extraction_request_id": request_id,
            },
            page=0,
            page_size=1,
        )
        rows = result["rows"]
        if not rows:
            return {"status": "error", "error": "attachment_not_found"}
    elif attachment.conversation_id != conversation_id:
        return {"status": "error", "error": "attachment_not_found"}
    try:
        document = module_sdk.knowledge.get_extracted_document(request_id)
    except (PermissionError, RuntimeError, ValueError) as exc:
        return {
            "status": "error",
            "error": str(exc),
            "request_id": request_id,
        }
    markdown = str(document.get("markdown_content") or "")
    budget = _document_budget_chars(context)
    truncated = len(markdown) > budget
    returned_markdown = markdown[:budget] if truncated else markdown
    return {
        "status": "ok",
        "request_id": request_id,
        "title": document.get("title"),
        "mime_type": document.get("mime_type"),
        "chunks_count": document.get("chunks_count"),
        "markdown": returned_markdown,
        "truncated": truncated,
        "original_chars": len(markdown),
        "returned_chars": len(returned_markdown),
        "budget_chars": budget,
    }


_DEFAULT_READ_BUDGET_CHARS = 12000


def _document_budget_chars(context: dict[str, Any] | None) -> int:
    return (
        int((context or {}).get("tool_result_budget_chars") or 0)
        or _DEFAULT_READ_BUDGET_CHARS
    )


def _resolve_document_request_id(
    module_sdk: Any,
    *,
    conversation_id: int,
    attachment_id: int | str,
    extraction_request_id: str,
) -> tuple[str | None, str | None]:
    """Return (request_id, error). Mirrors get-document-markdown scoping."""
    request_id = str(extraction_request_id or "").strip()
    attachment = None
    if not request_id and int(attachment_id or 0) > 0:
        attachment = module_sdk.database.get(Attachment, int(attachment_id))
        if attachment is not None:
            request_id = attachment.extraction_request_id
    if not request_id:
        return None, "extraction_request_id_required"
    if attachment is None:
        result = Attachment.list(
            filters={
                "conversation_id": conversation_id,
                "extraction_request_id": request_id,
            },
            page=0,
            page_size=1,
        )
        if not result["rows"]:
            return None, "attachment_not_found"
    elif attachment.conversation_id != conversation_id:
        return None, "attachment_not_found"
    return request_id, None


@tool(
    "read-document",
    title="Read document for analysis",
    description=(
        "Read an uploaded document for analysis. Every result includes counts "
        "(items per type, e.g. how many tables). Without blocks: returns the "
        "whole document if it fits the context, otherwise an index of its blocks "
        "(index + preview). With blocks: returns the content of those block "
        "indexes; any left out for size are listed in not_returned, request them "
        "in a follow-up call. Use kind to choose what to read: chunk (default "
        "text), table, formula or image."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "attachment_id": {"type": "integer"},
            "extraction_request_id": {"type": "string"},
            "blocks": {"type": "array", "items": {"type": "integer"}},
            "kind": {
                "type": "string",
                "enum": ["chunk", "table", "formula", "image"],
            },
        },
    },
)
def read_document(
    attachment_id: int | str = 0,
    extraction_request_id: str = "",
    blocks: list[int] | None = None,
    kind: str = "chunk",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_sdk = _sdk(sdk)
    conversation_id = _conversation_id(context)
    if conversation_id <= 0:
        return {"status": "error", "error": "conversation_id_required"}
    request_id, error = _resolve_document_request_id(
        module_sdk,
        conversation_id=conversation_id,
        attachment_id=attachment_id,
        extraction_request_id=extraction_request_id,
    )
    if error is not None:
        return {"status": "error", "error": error}
    budget = _document_budget_chars(context)
    resolved_blocks = [int(value) for value in blocks] if blocks else None
    try:
        payload = module_sdk.knowledge.read_document_blocks(
            request_id=request_id,
            max_chars=budget,
            blocks=resolved_blocks,
            kind=str(kind or "chunk"),
        )
    except (PermissionError, RuntimeError, ValueError) as exc:
        return {"status": "error", "error": str(exc), "request_id": request_id}
    if payload.get("mode") == "index":
        document_summary = _document_summary(module_sdk, request_id)
        if document_summary:
            payload["document_summary"] = document_summary
    return {"status": "ok", **payload}


_SUMMARY_SECTION_SYSTEM = (
    "You summarize a large section of a document for later retrieval. Return "
    "compact markdown with: main topics, key facts, names/terms, and where a "
    "reader should search in this section. No preamble."
)
_REDUCE_SYSTEM = (
    "You are given ordered section summaries of one document. Build a compact "
    "document map for a chat assistant with: overall summary, search index by "
    "section, key terms, and guidance on which section to read for common "
    "questions. Keep section numbers."
)
_SUMMARY_SECTION_MAX_TOKENS = 320
_REDUCE_MAX_TOKENS = 800
_SUMMARY_SECTION_BUDGET_RATIO = 0.85
_SUMMARY_SECTION_MIN_CHARS = 256


def _completion_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")
    return str(content or "").strip()


def _document_summary(module_sdk: Any, request_id: str) -> str:
    items = module_sdk.knowledge.list_items_for_summary(
        request_id=request_id, item_type="document"
    )
    if not items:
        return ""
    return str(items[0].get("summary") or "").strip()


def _store_document_summary(module_sdk: Any, request_id: str, summary: str) -> bool:
    items = module_sdk.knowledge.list_items_for_summary(
        request_id=request_id, item_type="document"
    )
    if not items:
        return False
    return module_sdk.knowledge.store_item_summary(
        item_id=items[0]["id"],
        summary=summary,
    )


def _summary_section_budget_chars(context: dict[str, Any] | None) -> int:
    budget = int(_document_budget_chars(context))
    return max(_SUMMARY_SECTION_MIN_CHARS, int(budget * _SUMMARY_SECTION_BUDGET_RATIO))


def _split_long_text(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    remaining = text.strip()
    while len(remaining) > max_chars:
        cut = remaining.rfind("\n", 0, max_chars)
        if cut < max_chars // 2:
            cut = remaining.rfind(" ", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def _markdown_units(markdown: str) -> list[str]:
    units: list[str] = []
    current: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^#{1,6}\s+", line) and current:
            units.append("\n".join(current).strip())
            current = [line]
            continue
        if not line.strip():
            if current:
                units.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        units.append("\n".join(current).strip())
    return [unit for unit in units if unit]


def _split_markdown_sections(markdown: str, max_chars: int) -> list[str]:
    units = _markdown_units(markdown)
    if not units:
        return []
    sections: list[str] = []
    current: list[str] = []
    current_chars = 0
    for unit in units:
        if len(unit) > max_chars:
            if current:
                sections.append("\n\n".join(current).strip())
                current = []
                current_chars = 0
            sections.extend(_split_long_text(unit, max_chars))
            continue
        extra = len(unit) + (2 if current else 0)
        if current and current_chars + extra > max_chars:
            sections.append("\n\n".join(current).strip())
            current = [unit]
            current_chars = len(unit)
            continue
        current.append(unit)
        current_chars += extra
    if current:
        sections.append("\n\n".join(current).strip())
    return sections


@tool(
    "extract-full-summary",
    title="Summarize a document",
    description=(
        "Build (and cache) the analysis map of an uploaded document on the "
        "document summary record, using the current model. Returns the cached "
        "document map when it already exists."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "attachment_id": {"type": "integer"},
            "extraction_request_id": {"type": "string"},
        },
    },
)
async def extract_full_summary(
    attachment_id: int | str = 0,
    extraction_request_id: str = "",
    refresh: bool = False,
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_sdk = _sdk(sdk)
    conversation_id = _conversation_id(context)
    if conversation_id <= 0:
        return {"status": "error", "error": "conversation_id_required"}
    request_id, error = _resolve_document_request_id(
        module_sdk,
        conversation_id=conversation_id,
        attachment_id=attachment_id,
        extraction_request_id=extraction_request_id,
    )
    if error is not None:
        return {"status": "error", "error": error}

    cached_summary = _document_summary(module_sdk, request_id)
    if cached_summary:
        return {
            "status": "ok",
            "request_id": request_id,
            "summary": cached_summary,
            "cached": True,
            "sections_total": 0,
            "sections_summarized": 0,
            "source_chars": 0,
            "budget_chars": _summary_section_budget_chars(context),
            "sections_failed": [],
        }

    model_registry_id = int((context or {}).get("model_registry_id") or 0)
    if model_registry_id <= 0:
        return {"status": "error", "error": "model_registry_id_unavailable"}
    provider_result = await module_sdk.ai.get_provider_by_model_registry_id(
        model_registry_id
    )
    if provider_result.get("status") != "ok":
        return {
            "status": "error",
            "error": provider_result.get("error") or "provider_unavailable",
        }
    provider = provider_result["provider"]

    try:
        document = module_sdk.knowledge.get_extracted_document(request_id)
    except (PermissionError, RuntimeError, ValueError) as exc:
        return {"status": "error", "error": str(exc), "request_id": request_id}
    markdown = str(document.get("markdown_content") or "").strip()
    if not markdown:
        return {
            "status": "error",
            "error": "document_markdown_missing",
            "request_id": request_id,
        }

    section_budget = _summary_section_budget_chars(context)
    sections = _split_markdown_sections(markdown, section_budget)
    if not sections:
        return {
            "status": "error",
            "error": "document_sections_missing",
            "request_id": request_id,
        }

    module_sdk.system.log(
        f"[extract-full-summary] {request_id}: {len(markdown)} chars, "
        f"{len(sections)} sections, building document map"
    )
    summarized = 0
    failed: list[dict[str, Any]] = []
    section_summaries: list[str] = []
    for position, content in enumerate(sections, start=1):
        module_sdk.system.log(
            f"[extract-full-summary] summarizing section {position}/{len(sections)}"
        )
        try:
            response = await provider.generate_completion(
                messages=[
                    {"role": "system", "content": _SUMMARY_SECTION_SYSTEM},
                    {
                        "role": "user",
                        "content": f"Section {position}/{len(sections)}:\n\n{content}",
                    },
                ],
                options={"max_tokens": _SUMMARY_SECTION_MAX_TOKENS, "temperature": 0.3},
            )
            summary = _completion_text(response)
        except Exception as exc:
            module_sdk.system.log(
                f"[extract-full-summary] section {position} failed: {exc}",
                level="warning",
            )
            failed.append({"section": position, "error": str(exc)})
            continue
        if not summary:
            module_sdk.system.log(
                "[extract-full-summary] empty section summary",
                level="warning",
            )
            failed.append({"section": position, "error": "empty_summary"})
            continue
        section_summaries.append(f"Section {position}: {summary}")
        summarized += 1

    doc_summary = ""
    if section_summaries:
        try:
            response = await provider.generate_completion(
                messages=[
                    {"role": "system", "content": _REDUCE_SYSTEM},
                    {"role": "user", "content": "\n\n".join(section_summaries)},
                ],
                options={"max_tokens": _REDUCE_MAX_TOKENS, "temperature": 0.3},
            )
            doc_summary = _completion_text(response)
        except Exception as exc:
            failed.append({"section": -1, "error": f"reduce_failed:{exc}"})
        if doc_summary:
            updated = _store_document_summary(module_sdk, request_id, doc_summary)
            if not updated:
                module_sdk.system.log(
                    "[extract-full-summary] document summary store failed",
                    level="warning",
                )

    module_sdk.system.log(
        f"[extract-full-summary] done {request_id}: sections={len(sections)} "
        f"summarized={summarized} failed={len(failed)} "
        f"doc_summary={'yes' if doc_summary else 'no'}"
    )
    return {
        "status": "ok",
        "request_id": request_id,
        "summary": doc_summary,
        "cached": False,
        "sections_total": len(sections),
        "sections_summarized": summarized,
        "source_chars": len(markdown),
        "budget_chars": section_budget,
        "sections_failed": failed,
    }
