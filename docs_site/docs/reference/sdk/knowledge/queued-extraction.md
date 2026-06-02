# SDK Knowledge: Queued Extraction

Queued extraction is the durable background path used for uploaded media.

`enqueue_extraction(...)` creates the extraction request. Upload flows can also
create it automatically and return `extraction_request_id` in the upload
payload.

## Runtime Independence

Extraction and knowledge retrieval are separate concerns.

When knowledge runtime is disabled, `get_runtime_config()["enabled"]` is
`False` and retrieval through `retrieve(...)` is not available. The extraction
queue can still persist extracted items, including the complete markdown
document. Modules that need uploaded document content should therefore check
runtime config and fall back to `get_extracted_document(...)` when retrieval is
not available.

## `get_extraction_status(request_id: str) -> dict`

Returns scoped status for one extraction request owned by the current request
context.

```python
status = module_sdk.knowledge.get_extraction_status(request_id)
```

The returned payload has this shape:

```python
{
    "request_id": request_id,
    "extraction_status": "pending",
    "ready": False,
    "knowledge_enabled": False,
    "markdown_ready": False,
    "embedding_ready": False,
    "document_ingestion_status": "missing",
    "ingestion_request_status": "missing",
    "extractor_id": None,
    "mime_type": "application/pdf",
    "filename": "document.pdf",
    "last_error": None,
    "created_at": "2026-05-20T10:00:00",
    "started_at": None,
    "completed_at": None,
}
```

`extraction_status` reflects the durable extraction request status:

- `pending`
- `processing`
- `completed`
- `failed`
- `dead_letter`

`markdown_ready` becomes true when the extracted `document` item exists and has
stored markdown content.

`embedding_ready` is true only when knowledge is enabled and at least one
knowledge item derived from the extraction has a vector status of `ready` or
`synced`.

If the request is missing or outside the current scope, the method raises
`RuntimeError("knowledge_extraction_request_not_found")`.

## `list_extraction_statuses(request_ids: list[str]) -> dict`

Returns scoped status records for multiple extraction requests.

```python
result = module_sdk.knowledge.list_extraction_statuses(request_ids)
```

Shape:

```python
{
    "items": [status],
    "missing_request_ids": ["..."],
}
```

The batch method does not expose whether a missing id is absent or outside the
current scope.

## `get_extracted_document(request_id: str) -> dict`

Returns the complete markdown extracted for the `document` item of a completed
request.

```python
document = module_sdk.knowledge.get_extracted_document(request_id)
markdown = document["markdown_content"]
```

Shape:

```python
{
    "request_id": request_id,
    "extraction_status": "completed",
    "title": "document.pdf",
    "mime_type": "application/pdf",
    "markdown_content": "# Extracted document\n...",
    "chunks_count": 12,
    "metadata": {},
}
```

Errors:

- `RuntimeError("knowledge_extraction_request_not_found")`
- `RuntimeError("knowledge_extraction_request_not_completed")`
- `RuntimeError("knowledge_extracted_document_markdown_missing")`

Use this method when an agent needs the full document content or when knowledge
runtime is disabled and embedding retrieval cannot be used.
