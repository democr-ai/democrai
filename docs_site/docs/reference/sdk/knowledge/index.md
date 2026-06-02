# SDK Domain: `knowledge`

## Overview

The `knowledge` domain is the SDK surface modules use when they want higher-level document extraction or knowledge-ingestion entry points instead of working directly with the extractor runtime.

This domain sits one level above `sdk.extractors`.

That distinction matters:

- `sdk.extractors` is about extractor discovery, routing, and execution
- `sdk.knowledge` is about document-oriented workflows built on top of those extractor capabilities

In practice, `sdk.knowledge` currently gives you these categories of operations:

1. runtime configuration helpers for enabling knowledge and selecting models
2. document extraction helpers that wrap the registered extractor flow
3. durable extraction queue helpers for media that already exists in storage
4. scoped queued-extraction status and extracted-document readers
5. scoped extracted-item readers, search, and summary helpers
6. scoped retrieval helpers that query the configured knowledge runtime
7. scoped source and metadata deletion helpers

The runtime storage used behind those entry points is configured by the
application, not by modules.

## Mental Model

The safest way to reason about this domain is:

- if you want to choose or run an extractor directly, start with `sdk.extractors`
- if you want a document-oriented helper that already expresses a knowledge use case, start with `sdk.knowledge`

That means `sdk.knowledge` is not a low-level repository API. It is a scoped façade around document extraction, ingestion, queued extraction, and retrieval entry points.

## What This Domain Is For

Use `sdk.knowledge` when your module needs to:

- extract structured document content from a path that should behave like a knowledge document
- resolve or run the currently registered extractor through a knowledge-oriented API surface
- enqueue extraction for an existing media storage path with `enqueue_extraction(...)`
- read the scoped status of queued extraction requests
- retrieve the complete extracted markdown document for a completed request
- inspect extracted document blocks and extracted items without reading storage directly
- cache summaries for extracted items through the SDK scope contract
- delete owned knowledge sources or module-scoped metadata matches
- retrieve visible knowledge with `retrieve(...)`

Do not use it when your real task is "inspect which extractor would match this file" or "manage extractor runtime behavior". That belongs to `sdk.extractors`.

## Current Practical Scope

Today, the runtime configuration and extraction sides of this domain are
concrete and directly useful.

The runtime configuration is stored in the database. It controls whether
knowledge is enabled and which active model registry rows are used for:

- embedding
- reranking
- classification
- triples extraction

Embedding is required when knowledge is enabled. The selected embedding model
must have an embedding dimension configured on the model registry row
(`extra_config.dim`) because vector indexes and stored item metadata depend on
that dimension.

`enqueue_extraction(...)` persists a request in the application extraction queue. It does not run the extractor inline and it can be used when a module has already stored a file in media storage and wants the background knowledge flow to pick it up.

Queued extraction is distinct from knowledge runtime retrieval. A completed
extraction can expose the full extracted markdown through
`get_extracted_document(...)` even when the knowledge runtime is disabled. In
that case vector retrieval is unavailable, but modules can still use the
markdown produced by the extractor.

Ingestion is queue-oriented. Runtime flows that need to ingest uploaded or
extracted content create durable extraction/ingestion requests for the
background knowledge runtime; they do not depend on an in-memory knowledge
service in the caller process.

Retrieval is exposed as an async SDK method backed by the application
Knowledge Query Service. The service runs inside the core process, next to the
background knowledge runtime, so it can reuse the configured knowledge service
and graph store safely. It uses the current request context for user,
organization, and access level. Modules do not pass ownership fields to
retrieval directly.

## Subsections

This domain is split into focused pages:

- Document Extraction
- Working With Registered Extractors
- Queued Extraction
- Ingesting Documents
- Retrieving Knowledge
- Knowledge Runtime Storage

That order matches the practical progression most module authors follow: first get usable document content, then understand the lower bridge to registered extractors, then decide whether ingestion is the right next step.
