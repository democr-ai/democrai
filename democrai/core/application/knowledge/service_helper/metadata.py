"""Metadata enrichment helpers for cross-media knowledge ingestion.

The knowledge subsystem ingests documents, chats, transcripts, image
descriptions, and agent traces through the same item model. This module
normalizes metadata so retrieval and graph projection can reason about source
kind, granularity, and temporal references without hard-coding behavior in each
extractor.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from typing import Any

from democrai.core.application.knowledge.models import KnowledgeIngestItem
from democrai.core.application.knowledge.models import KnowledgeSourceInput


_ISO_DATETIME_RE = re.compile(
    r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"(?:[T\s](?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?)?\b"
)
_SLASH_DATE_RE = re.compile(
    r"\b(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})"
    r"(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2}))?\b"
)
_YEAR_MONTH_RE = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})\b")
_YEAR_RE = re.compile(r"\b(?P<year>19\d{2}|20\d{2}|21\d{2})\b")

_SCOPE_BY_KIND = {
    "document_summary": "summary",
    "chapter_summary": "summary",
    "paragraph_summary": "summary",
    "table_summary": "summary",
    "formula_summary": "summary",
    "image_summary": "summary",
    "transcript_summary": "summary",
    "document_index": "index",
    "document_transcript": "segment",
    "document_chunk": "raw",
    "chat_turn": "message",
    "agent_message": "message",
    "agent_trace": "trace",
}

_TIER_BY_SCOPE = {
    "summary": 1,
    "document": 1,
    "chapter": 1,
    "paragraph": 2,
    "segment": 2,
    "transcript": 2,
    "message": 2,
    "index": 3,
    "chunk": 3,
    "paragraph_chunk": 3,
    "raw": 3,
    "trace": 4,
}


def enrich_ingest_item(
    *,
    source: KnowledgeSourceInput,
    item: KnowledgeIngestItem,
) -> KnowledgeIngestItem:
    """Return a copy of the item enriched with normalized retrieval metadata.

    Enrichment adds source classification, normalized item scope, retrieval
    tier, and extracted temporal hints. The function never mutates the input
    dataclass instance.
    """
    metadata = dict(item.metadata or {})
    source_kind = infer_source_kind(
        source_type=source.source_type,
        mime_type=source.mime_type,
        item_kind=item.kind,
    )
    item_scope = (
        str(metadata.get("item_scope") or infer_item_scope(item_kind=item.kind)).strip()
        or "raw"
    )
    metadata.setdefault("source_type", source.source_type)
    metadata.setdefault("source_kind", source_kind)
    metadata.setdefault("item_kind", item.kind)
    metadata["item_scope"] = item_scope
    metadata.setdefault("retrieval_tier", infer_retrieval_tier(item_scope=item_scope))
    temporal = extract_temporal_metadata(
        title=item.title,
        summary=item.summary,
        content=item.content,
        metadata=metadata,
    )
    for key, value in temporal.items():
        metadata.setdefault(key, value)
    return replace(item, metadata=metadata)


def infer_source_kind(
    *,
    source_type: str | None,
    mime_type: str | None,
    item_kind: str | None,
) -> str:
    """Infer the broad media family for an ingested source/item pair."""
    source_name = str(source_type or "").strip().lower()
    mime_name = str(mime_type or "").strip().lower()
    kind_name = str(item_kind or "").strip().lower()
    if "chat" in source_name or "chat_" in kind_name:
        return "chat"
    if "agent" in source_name or "agent_" in kind_name:
        return "agent"
    if mime_name.startswith("image/"):
        return "image"
    if mime_name.startswith("audio/"):
        return "audio"
    if mime_name.startswith("video/"):
        return "video"
    if source_name in {"image", "audio", "video", "document"}:
        return source_name
    return "document"


def infer_item_scope(*, item_kind: str | None) -> str:
    """Infer the retrieval granularity associated with an item kind."""
    kind_name = str(item_kind or "").strip().lower()
    if kind_name in _SCOPE_BY_KIND:
        return _SCOPE_BY_KIND[kind_name]
    if kind_name.endswith("_summary"):
        return "summary"
    if "chunk" in kind_name:
        return "chunk"
    if "transcript" in kind_name:
        return "transcript"
    if "index" in kind_name:
        return "index"
    if "chat" in kind_name or "message" in kind_name:
        return "message"
    return "raw"


def infer_retrieval_tier(*, item_scope: str | None) -> int:
    """Map a normalized item scope to a retrieval tier.

    Lower tier numbers represent higher-level, summary-oriented material that
    should usually rank before raw chunks.
    """
    scope_name = str(item_scope or "").strip().lower()
    return _TIER_BY_SCOPE.get(scope_name, 3)


def extract_temporal_metadata(
    *,
    title: str | None,
    summary: str | None,
    content: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Extract the first grounded temporal reference found in the item text."""
    existing = dict(metadata or {})
    if existing.get("time_iso"):
        return _normalize_existing_temporal(existing)

    text = "\n".join(
        part.strip() for part in (title, summary, content) if str(part or "").strip()
    )
    if not text:
        return _normalize_existing_temporal(existing)

    for parser in (
        _parse_iso_datetime,
        _parse_slash_date,
        _parse_year_month,
        _parse_year,
    ):
        parsed = parser(text)
        if parsed:
            return parsed
    return _normalize_existing_temporal(existing)


def _normalize_existing_temporal(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in (
        "time_iso",
        "time_year",
        "time_month",
        "time_day",
        "time_hour",
        "time_minute",
        "time_granularity",
    ):
        value = metadata.get(key)
        if value not in (None, ""):
            normalized[key] = value
    if normalized and "time_granularity" not in normalized:
        normalized["time_granularity"] = _infer_granularity(normalized)
    return normalized


def _parse_iso_datetime(text: str) -> dict[str, Any]:
    match = _ISO_DATETIME_RE.search(text)
    if match is None:
        return {}
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    hour = int(match.group("hour")) if match.group("hour") is not None else None
    minute = (
        int(match.group("minute")) if match.group("minute") is not None else None
    )
    payload = {
        "time_year": year,
        "time_month": month,
        "time_day": day,
    }
    if hour is not None:
        payload["time_hour"] = hour
    if minute is not None:
        payload["time_minute"] = minute
    payload["time_granularity"] = _infer_granularity(payload)
    payload["time_iso"] = _build_iso(payload)
    return payload


def _parse_slash_date(text: str) -> dict[str, Any]:
    match = _SLASH_DATE_RE.search(text)
    if match is None:
        return {}
    payload = {
        "time_year": int(match.group("year")),
        "time_month": int(match.group("month")),
        "time_day": int(match.group("day")),
    }
    if match.group("hour") is not None:
        payload["time_hour"] = int(match.group("hour"))
    if match.group("minute") is not None:
        payload["time_minute"] = int(match.group("minute"))
    payload["time_granularity"] = _infer_granularity(payload)
    payload["time_iso"] = _build_iso(payload)
    return payload


def _parse_year_month(text: str) -> dict[str, Any]:
    match = _YEAR_MONTH_RE.search(text)
    if match is None:
        return {}
    payload = {
        "time_year": int(match.group("year")),
        "time_month": int(match.group("month")),
    }
    payload["time_granularity"] = _infer_granularity(payload)
    payload["time_iso"] = _build_iso(payload)
    return payload


def _parse_year(text: str) -> dict[str, Any]:
    match = _YEAR_RE.search(text)
    if match is None:
        return {}
    payload = {"time_year": int(match.group("year"))}
    payload["time_granularity"] = _infer_granularity(payload)
    payload["time_iso"] = _build_iso(payload)
    return payload


def build_time_node_payload(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Build the normalized payload used to project a ``TimeExpression`` node."""
    normalized = _normalize_existing_temporal(dict(metadata or {}))
    if not normalized:
        return {}
    payload = dict(normalized)
    payload["time_iso"] = str(payload.get("time_iso") or _build_iso(payload)).strip()
    if not payload["time_iso"]:
        return {}
    payload["node_id"] = f"time:{payload['time_iso']}"
    return payload


def _infer_granularity(payload: dict[str, Any]) -> str:
    if payload.get("time_hour") is not None:
        return "hour"
    if payload.get("time_day") is not None:
        return "day"
    if payload.get("time_month") is not None:
        return "month"
    return "year"


def _build_iso(payload: dict[str, Any]) -> str:
    year = payload.get("time_year")
    if year is None:
        return ""
    month = payload.get("time_month")
    day = payload.get("time_day")
    hour = payload.get("time_hour")
    minute = payload.get("time_minute")
    if hour is not None:
        return datetime(
            int(year),
            int(month or 1),
            int(day or 1),
            int(hour),
            int(minute or 0),
        ).strftime("%Y-%m-%dT%H:%M")
    if day is not None:
        return datetime(int(year), int(month or 1), int(day)).strftime("%Y-%m-%d")
    if month is not None:
        return f"{int(year):04d}-{int(month):02d}"
    return f"{int(year):04d}"
