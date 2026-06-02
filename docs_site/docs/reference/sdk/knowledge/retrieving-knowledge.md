# Retrieving Knowledge

This section covers scoped read, search, summary, delete, and retrieval methods
exposed by the `knowledge` façade:

- `retrieve(...)`
- `read_document_blocks(...)`
- `list_items_for_summary(...)`
- `store_item_summary(...)`
- `search_extracted_items(...)`
- `delete_source(...)`
- `delete_by_metadata(...)`

Retrieval is scoped automatically. Module code does not provide `user_id`,
`organization_id`, or `access_level`; those values come from the active request
context.

## Shared Preconditions

Retrieval requires:

- the Knowledge Query Service to be reachable
- an active request context
- an authenticated user id in that request context

The query service is started by the core runtime on the core network loop. It
is a service boundary for engine/tool runtimes, not a separate process that
opens knowledge storage independently.

If the query service is unavailable, the method raises a runtime error from the
query client.

```text
RuntimeError("knowledge_query_not_ready")  # startup/health check
RuntimeError("knowledge_query_retrieve_failed")  # retrieval RPC failure
```

If no request context is active, the method raises:

```text
RuntimeError("knowledge_retrieval_missing_request_context")
```

If the request context does not contain a user id, the method raises:

```text
RuntimeError("knowledge_retrieval_missing_user_id")
```

## `await retrieve(query_text, query_vector=None, top_k=8, lexical_limit=8, graph_neighbors_limit=4, metadata_filters=None)`

This method asks the application Knowledge Query Service to run hybrid retrieval
for the current request user.

Example:

```python
result = await module_sdk.knowledge.retrieve(
    query_text="budget planning",
    top_k=5,
    metadata_filters={"module_name": "docs"},
)

for match in result.matches:
    print(match.title, match.score)
```

## What It Is For

Use this when your module needs knowledge matches visible to the current user.

Typical cases:

- contextual search inside a module page or action
- retrieving supporting documents for an AI workflow
- narrowing knowledge results with metadata filters
- showing graph-neighbor context alongside retrieved items
- reconciling chat attachment context for a known AI pipeline

## What It Does

The method:

1. resolves `user_id`, `organization_id`, and `access_level` from the request context
2. validates that `query_text` is non-empty
3. builds a `KnowledgeRetrieveRequest`
4. sends the request to the Knowledge Query Service

The core retrieval service handles lexical search, vector search, optional
reranking, graph expansion, and graph-neighbor enrichment according to the
active runtime configuration.

When `metadata_filters["pipeline_id"]` is provided, retrieval can merge chat
attachment context for media-derived knowledge items linked to that pipeline.
Without `pipeline_id`, upload context is not merged.

## Scope Behavior

Retrieval applies the knowledge visibility rules in the backend.

For a normal module call, the practical rule is:

- the current user's own knowledge is visible
- public knowledge visible to that request scope is visible
- private knowledge owned by other users is not visible

The SDK does not expose parameters to override this scope. If a module needs
retrieval, it should call `module_sdk.knowledge.retrieve(...)` and let the
runtime apply the current request context.

## Validation Behavior

If `query_text` is empty after normalization, the method raises:

```text
ValueError("query_text is required")
```

`top_k`, `lexical_limit`, and `graph_neighbors_limit` are normalized to integers
before the request reaches the knowledge service.

## Return Value

The method returns the result from the knowledge service.

The intended return shape is `KnowledgeRetrieveResult`, which contains:

- `matches`

Each match is a `KnowledgeRetrieveMatch` with:

- `item_id`
- `source_id`
- `kind`
- `title`
- `content`
- `summary`
- `score`
- `metadata`
- `graph_neighbors`

## Notes For Module Authors

`retrieve(...)` is async because the Knowledge Query Service can call async
vector and graph providers.

Do not read knowledge repository records directly from a module. Repository
methods are internal to the application layer and do not define the SDK scope
contract.

## Extracted Document Readers

Use `read_document_blocks(...)` when a module needs bounded access to extracted
document content without loading the whole markdown document.

```python
blocks = module_sdk.knowledge.read_document_blocks(
    request_id=request_id,
    max_chars=12000,
    kind="chunk",
)
```

If `blocks` is omitted, the method returns either the whole document when it
fits the character budget or an index of available items for the selected kind.
If `blocks` is provided, it returns those ordinals up to `max_chars`.

Supported `kind` values are the extraction item kinds produced by the runtime,
including `chunk`, `table`, `formula`, and `image`.

## Extracted Item Summary Helpers

Use `list_items_for_summary(...)` to read extracted items with their cached
summary state:

```python
items = module_sdk.knowledge.list_items_for_summary(
    request_id=request_id,
    item_type="chunk",
)
```

Use `store_item_summary(...)` to persist a summary for one extracted item:

```python
saved = module_sdk.knowledge.store_item_summary(
    item_id=item_id,
    summary=summary,
)
```

These helpers are scoped to the current request user and organization. The
summary cache is owned by the extraction runtime; module code should not update
repository rows directly.

## Searching Extracted Items

Use `search_extracted_items(...)` when the module needs lexical search across
extracted markdown or chunks visible to the current request scope.

```python
matches = module_sdk.knowledge.search_extracted_items(
    query_text="payment terms",
    limit=8,
    extraction_request_ids=[request_id],
)
```

The query text is required. `extraction_request_ids` can narrow the search to a
known set of extraction requests.

## Deleting Knowledge Data

Use `delete_source(source_id)` to soft-delete one owned knowledge source and
enqueue projection cleanup:

```python
deleted_item_ids = module_sdk.knowledge.delete_source(source_id)
```

Use `delete_by_metadata(...)` to delete records matching module-scoped metadata:

```python
result = module_sdk.knowledge.delete_by_metadata(
    {"conversation_id": str(conversation_id)},
    force=True,
)
```

The SDK injects the current module name into metadata filters. Callers must not
include `module_name` themselves. Ownership scope comes from the active request
context.
