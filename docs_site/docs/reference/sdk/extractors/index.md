# SDK Domain: `extractors`

## Overview

The `extractors` domain is the SDK surface modules use when they need to discover registered file extractors, configure MIME-type routing, resolve which extractor should handle a file, and run the actual extraction through the managed extractor runtime.

This domain is the right entry point when your problem is:

- "which extractor would handle this file?"
- "which extractors are installed or active right now?"
- "run the registered extractor for this document or binary payload"

It is not the same thing as `sdk.knowledge`.

`sdk.knowledge` is the higher-level document and ingestion facade. It may call into `sdk.extractors`, but extractor lookup and execution belong here.

## Mental Model

The extractor runtime has three distinct layers, and the SDK domain maps cleanly to them:

1. manifest discovery
2. registered extractor state
3. MIME-type binding
4. runtime execution

Manifest discovery tells you what extractor capabilities exist on disk.

Registered state tells you which extractor rows exist and whether they are operationally installed or active.

MIME-type binding tells you which installed extractor is selected for a source MIME type. Resolution uses that binding table; it does not invent an extension-priority fallback.

Runtime execution takes the resolved extractor and runs it inside the managed extractor runtime, returning normalized structured output.

Installation and runtime synchronization are lifecycle operations for installable extractors. They publish install events, check whether extractor dependencies are available on the current node, and keep the live runtime aligned with persisted active extractor rows.

That distinction matters because developers often mix up "an extractor exists in the codebase" with "an extractor is actually registered and available for this file right now". The SDK keeps those concerns separate.

## The Public Surface

The `Extractors` facade is intentionally small:

- `list_manifests()`
- `list_registered()`
- `list_configurable_mime_bindings()`
- `list_ingestible_mime_types()`
- `set_mime_type_binding(...)`
- `resolve(...)`
- `resolve_for_mime_type(...)`
- `request_install(...)`
- `sync_runtime()`
- `check_ready(...)`
- `extract(...)`
- `extract_with_registered(...)`
- `guess_mime_type(...)`

Even though the surface is compact, the domain is operationally important because document-oriented module flows often depend on choosing the right extractor deterministically.

## When To Use This Domain

Use `sdk.extractors` when you are building module features such as:

- attachment preprocessing
- file import flows
- document preview preparation
- extractor debug or admin tools
- file-type routing before ingestion

Use `sdk.knowledge` when your real goal is document ingestion, knowledge indexing, or higher-level knowledge workflows. In that case, `sdk.extractors` is still part of the stack, but not the abstraction you usually expose first to module users.

## Subsections

This domain is split into focused pages:

- Discovery and Resolution
- Installation and Runtime
- Running Extraction

That is the natural order in real module code: first decide which extractor should handle the source, install or synchronize lifecycle state when needed, then execute it.
