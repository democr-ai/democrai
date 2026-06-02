# Knowledge Application

This package owns document ingestion, extracted content, vector projection,
knowledge graph projection, retrieval and extractor runtime coordination.

It coordinates storage and AI services, but it is not itself a storage provider.

## Flow

```text
module/core request
  -> SDK knowledge/media API
  -> KnowledgeIngestionFacade
  -> KnowledgeRepository outbox
  -> KnowledgeRuntime
  -> extractor / embedding / triple extraction
  -> vector storage + KG storage
```

## Key Files

- `ingestion.py`: ingestion facade.
- `repository.py` and `repository_helper/`: records, extraction requests and
  outbox persistence.
- `runtime.py`: background knowledge processing worker.
- `service.py` and `service_helper/`: ingestion, retrieval, vector projection
  and graph projection.
- `embedding.py`: configured embedding provider access.
- `triples.py` and `triples_helper/`: entity and relation extraction.
- `extractor/`: external extractor discovery, installation and runtime.
- `extractors/`: core extractors when provided by the application.
- `visibility.py`: content visibility and scope rules.

## Extractors

External extractors are discovered from:

```bash
DEMOCRAI_EXTRACTORS_PATH
```

They use SDK extractor contracts and dedicated manifests. They must not import
core internals.

## Embeddings

The knowledge service uses the configured embedding provider to generate
vectors. Model selection goes through the AI orchestrator objective/capability
contracts.

Index dimensions must come from runtime model metadata or configuration. Avoid
loading models during bootstrap only to probe metadata that is already known.

## Storage

The knowledge domain uses:

- data storage for records, extraction requests and outbox state.
- vector storage for embeddings.
- KG storage for nodes, relations and evidence.

Modules and UI actions must not write directly to vector or KG providers.

## Runtime

The runtime processes work through queue/lease semantics and updates persistent
job state. It must distinguish:

- persistent job state.
- transient progress/UI events.
- recoverable errors and retry attempts.

## Rules

- Modules use SDK knowledge/media APIs.
- External extractors use SDK extractor contracts.
- Vector and KG providers stay behind the knowledge service.
- Do not duplicate chunking, retrieval or projection logic in UI actions.
- Avoid expensive AI model loading in bootstrap when metadata is sufficient.
