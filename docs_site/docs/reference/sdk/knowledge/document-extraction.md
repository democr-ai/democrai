# Document Extraction

This section covers the most directly useful high-level method in the domain:

- `extract_document_data(...)`

If you are a module author who wants document content in a knowledge-oriented shape without manually orchestrating extractor selection, this is usually the first method to look at.

## `extract_document_data(path, force_path_resolved=False, chunker_override=None, chunker_max_tokens=None, ocr_enabled=None)`

This method extracts structured content from a readable document path using the currently registered extractor flow.

Example:

```python
payload = module_sdk.knowledge.extract_document_data(
    "/tmp/report.pdf",
    chunker_override="markdown",
    chunker_max_tokens=800,
    ocr_enabled=True,
)
```

Example with a persisted media payload:

```python
payload = module_sdk.knowledge.extract_with_registered_extractor(
    data=module_sdk.media.view(document.media_path),
    filename="report.pdf",
)
```

## What It Is For

Use this when your module wants structured document content and the source is already available as a readable local path.

Typical examples:

- preprocessing an uploaded document before attaching it to a chat flow
- extracting markdown and chunks from a stored PDF
- building a document-summary or preview flow

This method is intentionally document-oriented. It is a convenience layer over the extractor runtime, not a generic routing primitive.

## What It Actually Does

Under the hood, the method:

1. rejects legacy path-resolution mode if `force_path_resolved=True`
2. guesses the mime type from the provided path
3. calls `sdk.extractors.extract(...)`
4. passes a config override dict containing:
   - `chunker`
   - `chunker_max_tokens`
   - `ocr_enabled`
5. raises a runtime error if no registered extractor matches

That final step is important.

This method does not silently return `None` when no extractor is available. It converts that condition into an explicit failure because the method represents a knowledge-level expectation: if you asked to extract a document, the operation is supposed to succeed through a registered extractor.

## About `force_path_resolved`

This flag is no longer a supported path-resolution mechanism.

If `force_path_resolved=True`, the method raises:

```text
RuntimeError("legacy media path resolution was removed from the public SDK; rewrite this extraction flow against the new media API")
```

Keep the argument documented only because it is still present in the current function signature. New module code should leave it at the default `False`.

If your source lives in persisted media storage rather than at a readable local path, the correct pattern is to load the bytes through `module_sdk.media.view(...)` and call `module_sdk.knowledge.extract_with_registered_extractor(...)` instead.

## Return Value

On success, the method returns the same normalized extraction payload produced by the registered extractor flow, including fields such as:

- `extractor_id`
- `structure`
- `markdown_content`
- `chunks`
- `index`
- `formulas`
- `tables`
- `images`
- `resolved_extractor`

That means the output is still extractor-derived, but the calling style is more document-oriented.

## Failure Behavior

If no registered extractor matches the provided path and guessed mime type, the method raises:

```text
RuntimeError("registered_extractor_not_found ...")
```

That makes this method stricter than `sdk.extractors.extract(...)`, which returns `None` when no extractor matches.

### Why This Difference Exists

The lower extractor domain is a routing/execution primitive. Returning `None` there makes sense because the caller may still want to decide what to do.

The knowledge façade is a higher-level helper. Here, missing extractor support is generally a real operational problem rather than just a neutral routing outcome.

## Real Usage Pattern

Document-oriented flows usually follow this split:

1. if you already have a readable local path, call `module_sdk.knowledge.extract_document_data(...)`
2. if you have a stored media reference, load the bytes with `module_sdk.media.view(...)`
3. pass those bytes to `module_sdk.knowledge.extract_with_registered_extractor(...)`
4. read the extracted markdown for downstream use

That keeps the extraction API aligned with the current public media contract.

## When To Use This Instead Of `sdk.extractors.extract(...)`

Prefer `extract_document_data(...)` when:

- you already have a readable local path
- your feature is document-centric
- failure to find an extractor should be treated as an error

Prefer `sdk.extractors.extract(...)` when:

- you need lower-level control
- you are dealing with bytes rather than a resolved path
- you want to inspect or handle the `None` case yourself

Prefer `module_sdk.knowledge.extract_with_registered_extractor(...)` when:

- the document is already in memory as bytes
- the source came from `module_sdk.media.view(...)`
- you want the knowledge-domain entrypoint without relying on a local filesystem path
