# Working With Registered Extractors

This section covers the two bridge methods that expose extractor routing and execution through the `knowledge` facade:

- `resolve_registered_extractor(...)`
- `extract_with_registered_extractor(...)`

These methods exist for module authors who conceptually work in the knowledge domain but still need direct access to the registered-extractor path without dropping down into `sdk.extractors` explicitly.

## `resolve_registered_extractor(path=None, filename=None, mime_type=None) -> dict | None`

This method resolves the extractor bound to the source MIME type through
`sdk.extractors.resolve(...)`.

Example:

```python
resolved = module_sdk.knowledge.resolve_registered_extractor(
    filename="report.pdf",
    mime_type="application/pdf",
)
```

## What It Is For

Use this when your module wants to stay on the `knowledge` façade but still needs to know which registered extractor would be selected for a source.

Typical examples:

- deciding whether a document type is supported before starting a flow
- debugging why a document will route to a specific extractor
- surfacing extractor information in a document-oriented admin screen

## What It Does

The method:

1. normalizes `path`, `filename`, and `mime_type`
2. lowercases the mime type when present
3. delegates directly to `sdk.extractors.resolve(...)`

It does not add extra routing logic beyond that.

The current extractor resolver is binding-based. If the MIME type is not
configured in the extractor MIME binding table, this method returns `None` even
when an installed extractor declares theoretical support for the MIME type.

### What It Returns

The return value is the resolved extractor payload from the extractor domain, or `None` if no extractor matches.

That payload includes routing details such as:

- `row_id`
- `extractor_id`
- `status`
- `priority`
- `mime_match`
- `extension_match`

## Why This Method Exists

Strictly speaking, a module could call `module_sdk.extractors.resolve(...)` directly.

This helper exists to keep document-oriented code readable when the surrounding flow is already written in terms of the knowledge domain.

It is a convenience bridge, not a separate subsystem.

## `extract_with_registered_extractor(path=None, data=None, filename=None, mime_type=None, config=None) -> dict | None`

This method runs the active registered extractor through `sdk.extractors.extract(...)`.

Example with bytes:

```python
payload = module_sdk.knowledge.extract_with_registered_extractor(
    data=file_bytes,
    filename="contract.pdf",
    mime_type="application/pdf",
    config={"ocr_enabled": True},
)
```

Example with a path:

```python
payload = module_sdk.knowledge.extract_with_registered_extractor(
    path="/tmp/contract.pdf",
)
```

## What It Is For

Use this when you want the knowledge-domain naming but the extraction semantics of the registered extractor flow.

This is most useful when:

- the feature is knowledge-oriented
- you still want the lower extractor behavior of returning `None` instead of raising
- you want to pass raw bytes directly

## What It Does

The method:

1. normalizes `path`, `filename`, `mime_type`, and `config`
2. converts `data` to `bytes` when provided
3. delegates directly to `sdk.extractors.extract(...)`

Like `resolve_registered_extractor(...)`, this is a bridge method, not a separate runtime.

## Important Difference From `extract_document_data(...)`

This method returns `None` when no extractor matches, because it follows the lower extractor-domain behavior.

That makes it different from `extract_document_data(...)`, which raises a `RuntimeError` when no registered extractor is found.

### When To Choose Which

Use `extract_document_data(...)` when:

- you have a path
- the operation is document-centric
- missing extractor support should fail explicitly

Use `extract_with_registered_extractor(...)` when:

- you want to handle the `None` case yourself
- you are working with raw bytes
- you want a thinner bridge to the extractor facade

## Why These Methods Matter

It may seem redundant to expose extractor behavior through the knowledge domain, but in practice these bridge methods help keep module code cohesive.

Sometimes a feature is clearly about document knowledge, not extractor administration, yet it still needs just enough control to:

- inspect the resolved extractor
- run extraction without the stricter error behavior of `extract_document_data(...)`

These two methods solve that problem cleanly.
