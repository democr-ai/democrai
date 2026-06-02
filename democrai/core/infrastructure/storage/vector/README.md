# Vector Storage

This package owns persisted vector indexes and embeddings. It is used by the
knowledge runtime and by core services that need semantic search.

It does not choose embedding models. It receives vectors or an `IndexSpec` with
model metadata. AI model selection belongs to the AI/knowledge layers.

## Key Files

- `base.py`: `VectorProvider`, `IndexSpec`, `VectorDoc`, `Query`, `Match` and
  `Metric` contracts.
- `sqlite_vec_store.py`: local `sqlite-vec` provider on `vector.db`.
- `milvus_store.py`: Milvus provider.
- `pinecone_store.py`: Pinecone provider.
- `composite.py`: dual-write/read-fallback provider composition.
- `factory.py`: resolves provider from config/preferences.
- `models.py` and `migrations/`: local SQLite metadata/schema.

## Boundary

Correct flow:

```text
module
  -> SDK/knowledge API
  -> knowledge service
  -> vector store
```

Modules must not construct `VectorStoreFactory` or open global indexes.

## Scope

Vector operations are isolated by application scope:

- tenant/application/index from `IndexSpec`.
- user and organization when a user scope is provided.

Providers must preserve scope in:

- `upsert`
- `query`
- `delete_ids`
- `delete_by_filter`

## Providers

Local:

- `sqlite-vec`

Remote:

- `milvus`
- `pinecone`

Composite:

- writes to primary and secondary providers.
- reads from primary with fallback.
- supports controlled migrations and hybrid deployments.

## Embedding Dimension

Index dimensions come from `IndexSpec`. For knowledge indexes, the spec is built
from embedding runtime metadata/configuration.

The vector store must not load AI engines or call AI providers to discover
dimensions.

## Rules

- Do not put model selection logic in vector storage.
- Do not silently switch providers without configuration/preference.
- Do not treat SQLite without `sqlite-vec` as a vector provider.
- Keep portable metrics limited to the supported contract.
- Expose vector features through SDK/knowledge, not direct provider imports.
