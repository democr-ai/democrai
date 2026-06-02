# Ingesting Documents

Knowledge ingestion is queue-oriented.

Module code does not load extractors, embedding models, graph builders, or
knowledge services inline. It creates durable work for the background knowledge
runtime, then reads status and extracted content through scoped SDK methods.

## Correct Flow

For uploaded or media-backed files, the module flow is:

1. store or receive the file through the media/upload path;
2. keep the `extraction_request_id` when the upload path already produced one;
3. otherwise enqueue extraction with `enqueue_extraction(...)`;
4. poll or inspect status with `get_extraction_status(...)`;
5. use `retrieve(...)` when knowledge runtime is enabled and embeddings are ready;
6. use `get_extracted_document(...)` when the full markdown document is needed or
   knowledge runtime is disabled.

That split is intentional. Extraction can produce complete markdown even when
vector retrieval is not available.

## `enqueue_extraction(...)`

Use `enqueue_extraction(...)` when a file already exists in media storage and
your module needs the background extraction/ingestion runtime to process it.

```python
request_id = module_sdk.knowledge.enqueue_extraction(
    storage_path=stored_file.storage_path,
    filename=stored_file.original_filename,
    mime_type=stored_file.content_type,
    source_context={
        "conversation_id": conversation_id,
        "message_id": message_id,
    },
    metadata={
        "module_name": "chat",
        "conversation_id": conversation_id,
    },
    ingest=True,
)
```

The method returns the durable extraction request id.

### Parameters

| Parameter | Meaning |
| --- | --- |
| `storage_path` | Existing media storage path. Required. |
| `filename` | Optional display/source filename. Falls back to upload metadata. |
| `mime_type` | Optional MIME type. Falls back to upload metadata or filename guessing. |
| `metadata` | Metadata stored with the extraction/ingestion request. |
| `source_context` | Runtime context attached to the extraction request. |
| `ingest` | Whether completed extraction should also enqueue knowledge ingestion. |
| `priority` | Queue priority for background processing. |

The SDK resolves request identity from the active request context. Module code
does not pass `user_id`, `organization_id`, or access level manually.

## Upload Paths

Composer/upload flows can create the extraction request automatically. When the
upload payload already includes `extraction_request_id`, persist that id on the
module record instead of enqueueing the same media again.

The request id is the bridge between the user-facing module state and the
background knowledge runtime:

```python
attachment = Attachment.create(
    {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "filename": upload["filename"],
        "mime_type": upload["mime_type"],
        "storage_path": upload["storage_path"],
        "extraction_request_id": upload["extraction_request_id"],
    }
)
```

## Reading Status

Use status methods to decide what the agent or UI can do next.

```python
status = module_sdk.knowledge.get_extraction_status(request_id)

if status["markdown_ready"]:
    document = module_sdk.knowledge.get_extracted_document(request_id)
```

For multiple attachments:

```python
statuses = module_sdk.knowledge.list_extraction_statuses(request_ids)
```

The status payload tells you whether markdown and embeddings are ready, whether
knowledge is enabled, and whether ingestion has completed.

## Retrieval

When knowledge is enabled and embedding data is ready, use
`retrieve(...)` with metadata filters that keep the query inside the module
context you need.

```python
result = await module_sdk.knowledge.retrieve(
    query_text="invoice total",
    top_k=5,
    metadata_filters={
        "module_name": "chat",
        "conversation_id": str(conversation_id),
    },
)
```

Retrieval applies user and organization scope from the current request context.
Do not query knowledge storage directly from module code.

## Full Markdown Fallback

When knowledge runtime is not enabled, or when an agent needs the entire
document rather than chunks, read the extracted document:

```python
document = module_sdk.knowledge.get_extracted_document(request_id)
markdown = document["markdown_content"]
```

This works from completed extraction records and does not require vector
retrieval to be available.

## Direct Ingestion Helpers

The facade also exposes direct ingestion methods for module flows that already
have a readable document path or an in-memory byte payload.

Use `ingest_document(...)` for a document that already exists at a readable
path:

```python
result = module_sdk.knowledge.ingest_document(
    path="/tmp/import/report.pdf",
    title="Quarterly Report",
    metadata={"import_id": str(import_id)},
    is_public=False,
)
```

Use `ingest_document_bytes(...)` when the module has the document payload in
memory:

```python
result = module_sdk.knowledge.ingest_document_bytes(
    filename="report.pdf",
    data=payload,
    title="Quarterly Report",
    metadata={"import_id": str(import_id)},
)
```

Both methods resolve ownership from the active request context and inject the
current module name into metadata when it is not already present. They require
the knowledge ingestion runtime to be available.

Prefer `enqueue_extraction(...)` for uploaded media objects that already live in
the media store. Use these direct helpers only when the caller deliberately owns
the readable path or byte payload.

## What Modules Should Not Do

Module code should not:

- instantiate extractor providers directly for normal ingestion;
- instantiate embedding, rerank, classification, or graph models;
- access knowledge repository tables directly;
- depend on an in-memory knowledge service in the module process;
- pass ownership scope manually to retrieval.

The module owns its local records and user-facing state. The knowledge runtime
owns extraction, ingestion, projection, retrieval, and visibility rules.
