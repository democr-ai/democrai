# Knowledge Runtime Storage

This page documents the runtime storage contract behind `sdk.knowledge`.

It does not add a new SDK API. Modules still enter this domain through the public
SDK façade:

- `module_sdk.knowledge`
- `module_sdk.extractors`
- `module_sdk.media`

The storage providers described here are core runtime infrastructure. Module code
must not import or call them directly.

## Boundary

The knowledge storage flow is:

```text
module -> SDK knowledge/media API -> knowledge service -> vector/KG storage
```

That boundary matters because the storage layer is scoped, configured, and
initialized by the application runtime. A module should pass documents, bytes, or
media references through the SDK and let the runtime decide where the derived
knowledge projections are stored.

## Knowledge Graph Storage

The current supported knowledge graph providers are:

- `sqlite`
- `ladybug`
- `neo4j`

The local default is `sqlite`.

```yaml
storage:
  kg:
    type: sqlite
    # db_path: /path/to/kg.sqlite
```

When `db_path` is not configured, the SQLite provider uses:

```text
get_data_dir()/kg.sqlite
```

Ladybug remains available as an embedded graph provider:

```yaml
storage:
  kg:
    type: ladybug
    # db_path: /path/to/kg.lbug
```

Neo4j is the remote provider:

```yaml
storage:
  kg:
    type: neo4j
    uri: bolt://localhost:7687
    user: neo4j
    password: password
```

## Vector Storage

The current supported vector providers are:

- `sqlite-vec`
- `milvus`
- `pinecone`

The local default is `sqlite-vec`.

```yaml
storage:
  vector:
    type: sqlite-vec
    # index_prefix: democrai
```

SQLite without `sqlite-vec` is not a vector provider in the current contract.

Milvus requires a host:

```yaml
storage:
  vector:
    type: milvus
    host: localhost
    port: 19530
```

Pinecone requires an API key, either from configuration or from
`PINECONE_API_KEY`:

```yaml
storage:
  vector:
    type: pinecone
    api_key: ${PINECONE_API_KEY}
    cloud: aws
    region: us-east-1
```

## Runtime Configuration

Knowledge runtime configuration is database-backed and exposed through:

- `module_sdk.knowledge.get_runtime_config()`
- `module_sdk.knowledge.runtime_config_form_model()`
- `module_sdk.knowledge.update_runtime_config(...)`
- `module_sdk.knowledge.count_existing_embeddings()`

The persisted config has these fields:

- `enabled`
- `embedding_model_registry_id`
- `rerank_model_registry_id`
- `classification_model_registry_id`
- `triple_extractor_model_registry_id`

When `enabled=True`, `embedding_model_registry_id` is required. The selected
model must be active, must expose the `embedding` capability, and must have a
positive embedding dimension configured on the model registry row as
`extra_config.dim`.

The other model selections are optional:

- `rerank_model_registry_id` enables reranking when set
- `classification_model_registry_id` enables classification when set
- `triple_extractor_model_registry_id` enables knowledge-graph triple extraction when set

Each optional model is validated against its matching capability. There is no
global fallback model for classification, reranking, or triples extraction.

Changing the embedding model after embeddings already exist requires explicit
confirmation:

```python
try:
    module_sdk.knowledge.update_runtime_config(payload)
except RuntimeError as exc:
    if str(exc) == "knowledge_embedding_model_change_requires_rebuild":
        ...
```

After the user confirms the rebuild implication:

```python
module_sdk.knowledge.update_runtime_config(
    payload,
    confirm_embedding_model_change=True,
)
```

Use `count_existing_embeddings()` when a UI needs to explain why changing the
embedding model is risky.

## Vector Index Contract

Knowledge vector index configuration is driven by the database-backed runtime
configuration and the selected embedding model metadata.

The vector index stores:

- tenant id
- application id
- index name
- dimension
- metric
- embedding model id
- embedding model version

## Retrieval Configuration

Retrieval uses the configured embedding provider. If `rerank_model_registry_id`
is set, retrieval can rerank candidates through that model. If it is not set,
retrieval proceeds without a reranker.

## Chat Attachment Context

Uploaded chat attachments follow the same queued media path as other uploaded
documents. The upload step can enqueue extraction, but it does not necessarily
know the current chat message context yet.

The runtime therefore keeps a separate link between the uploaded media and the
chat pipeline context:

```text
file_id + user_id + organization_id + pipeline_id -> knowledge_chat_upload_contexts
```

When a chat message reaches the AI runtime, the runtime stores the current
pipeline context for each uploaded attachment by storage path. The repository
resolves the uploaded media record and stores one context row for
`file_id + user_id + organization_id + pipeline_id`. It does not require the canonical
knowledge source to exist yet, it does not read the attachment payload, and it
does not run knowledge ingestion inline.

The link is a read-time relation. Code that needs to reconstruct attachments for
a pipeline should query `knowledge_chat_upload_contexts` and join through
`file_id`. Queued extraction and ingestion do not read this table and do not
copy chat context into media-derived canonical records.

Pipeline fields remain inside the connection table `context` JSON. They are not
copied into media-derived `knowledge_sources` or `knowledge_items`.

Retrieval reconciles chat upload context only when the request filters by
`pipeline_id`.
It collects `knowledge_items.media_file_id` values from the visible candidate
set and performs one scoped, batched lookup in `knowledge_chat_upload_contexts`
for the current user, organization, and pipeline. For media-derived items with a
matching context, the context JSON is merged into the metadata returned by
retrieval.

When `pipeline_id` is supplied as a metadata filter, retrieval applies it with OR
semantics: normal knowledge items must match that metadata field directly, while
media-derived items can match through the upload context table. Without
`pipeline_id`, chat context is not merged, so retrieval never chooses an
arbitrary pipeline context. Writes, rebuilds, and projections still use the
canonical tables.

## Scope

Knowledge graph and vector operations are user-scoped.

The runtime also carries an optional `organization_id`. When no organization is
present, the storage layer uses its own internal representation for the no-org
scope. Module code should not depend on that representation.

From the module point of view, the rule is simple:

- use the SDK façade
- let the request context and configured providers define the storage scope

## Validation Behavior

Runtime configuration validation rejects unsupported storage provider values:

- `storage.kg.type` must be `sqlite`, `ladybug`, or `neo4j`
- `storage.vector.type` must be `sqlite-vec`, `milvus`, or `pinecone`

Provider-specific required fields are validated too:

- Neo4j requires `storage.kg.uri`, `storage.kg.user`, and
  `storage.kg.password`
- Milvus requires `storage.vector.host`
- Pinecone requires `storage.vector.api_key` unless `PINECONE_API_KEY` is set

## Ingestion Status

Knowledge ingestion is durable queue work.

Modules enqueue extraction for media-backed files, keep the returned
`extraction_request_id`, then inspect status and read either retrieved matches
or the complete extracted markdown.

Use the extraction APIs for concrete document processing behavior:

- `enqueue_extraction(...)`
- `get_extraction_status(...)`
- `list_extraction_statuses(...)`
- `get_extracted_document(...)`

Use `retrieve(...)` only when the knowledge runtime is enabled and the
requested content has embedding/knowledge data ready.
