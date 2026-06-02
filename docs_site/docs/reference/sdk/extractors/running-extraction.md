# Running Extraction

This section covers the operational method that most developers eventually need:

- `extract(...)`
- `extract_with_registered(...)`

This is the method that takes the current routing rules, resolves the correct registered extractor, and runs it through the managed extractor runtime.

## `extract(path=None, data=None, filename=None, mime_type=None, config=None) -> dict | None`

This method runs the active registered extractor selected by the configured MIME
type binding.

Example with a materialized media path:

```python
materialized = module_sdk.media.get_path(stored_path)
try:
    payload = module_sdk.extractors.extract(
        path=materialized.path,
        mime_type="application/pdf",
        config={"ocr_enabled": True},
    )
finally:
    materialized.cleanup()
```

Example with in-memory bytes:

```python
payload = module_sdk.extractors.extract(
    data=file_bytes,
    filename="report.pdf",
    mime_type="application/pdf",
    config={"chunker": "markdown"},
)
```

## What It Is For

Use this when your module wants the structured extraction output itself, not just the routing decision.

Typical examples:

- convert an uploaded PDF into markdown and chunks
- extract structure from a document before a chat or preview flow
- run the registered extractor configured for a MIME type

## Supported Input Shapes

You can call `extract(...)` in two main ways.

### Path-based extraction

Pass `path` when the file already exists at a readable local path.

If the source lives in media storage, first materialize it with
`module_sdk.media.get_path(...)` and pass the returned local path. Do not pass a
client media URL or proxy URL to the extractor.

### In-memory extraction

Pass `data` when the file exists only as bytes in memory.

When you use `data`, you should also pass:

- `filename`
- and, when available, `mime_type`

That gives the resolver enough information to choose the extractor deterministically.

## What Happens Internally

The facade does more than call one extractor class directly.

The flow is:

1. normalize `path`, `filename`, and `mime_type`
2. infer mime type from path or filename when missing
3. call `resolve(...)` to choose the extractor bound to that MIME type
4. merge extractor row config with any runtime overrides passed in `config`
5. prepare the input source list in the shape expected by the extractor runtime
6. call the managed extractor runtime
7. attach `resolved_extractor` metadata to the returned payload

That is why `extract(...)` is the right abstraction for modules. It preserves the full runtime contract instead of forcing every module to manually instantiate or route extractors itself.

## Return Value

When extraction succeeds, the returned payload contains normalized structured fields from the extractor runtime:

- `extractor_id`
- `structure`
- `markdown_content`
- `chunks`
- `index`
- `formulas`
- `tables`
- `images`
- `resolved_extractor`

That last field is added by the resolver layer and is particularly useful because it tells you which registered extractor row was actually selected.

### Why `resolved_extractor` Is Useful

When debugging an extraction result, it is often not enough to know only that extraction succeeded.

You also want to know:

- which extractor handled the file
- which MIME type binding selected it
- which config and registry metadata were attached to the chosen row

`resolved_extractor` gives you that context.

## Failure Behavior

This method has two important failure modes.

### No extractor matches

If the MIME type has no configured binding, or the bound extractor is no longer
installed/active, the method returns `None`.

It does not silently invent a fallback extractor.

That makes `None` a meaningful outcome your module must handle deliberately.

### No input was provided

If both `path` and `data` are missing, the lower resolver layer raises:

```text
ValueError("path or data is required")
```

That is a programmer error rather than a normal runtime result.

## Real Usage Pattern

The higher-level `sdk.knowledge.extract_document_data(...)` method delegates to this domain.

Its pattern is:

1. resolve or materialize the file path
2. call `sdk.extractors.extract(...)`
3. fail explicitly if the result is `None`

That is a good example of the relationship between `sdk.extractors` and `sdk.knowledge`:

- `sdk.extractors` is the lower-level execution domain
- `sdk.knowledge` can build stricter document-oriented behavior on top of it

## A Practical Module Example

Imagine a module that accepts uploaded attachments and wants to feed extracted text into a later workflow.

The pattern looks like this:

```python
payload = module_sdk.extractors.extract(
    data=file_bytes,
    filename="proposal.pdf",
    mime_type="application/pdf",
    config={
        "ocr_enabled": True,
        "chunker_max_tokens": 800,
    },
)

if payload is None:
    raise RuntimeError("registered_extractor_not_found")

markdown = str(payload.get("markdown_content") or "").strip()
chunks = list(payload.get("chunks") or [])
tables = list(payload.get("tables") or [])
```

This is the right style for module authors:

- let the extractor domain choose the runtime handler
- treat `None` as a real routing failure
- consume normalized output fields from the returned payload

## About `config`

The optional `config` parameter is not a separate extractor definition. It is a set of runtime overrides merged on top of the resolved extractor row config before execution.

That means it is appropriate for per-call behavior such as:

- enabling OCR
- selecting a chunker
- overriding token limits

It is not the same thing as permanently reconfiguring the extractor registry row.

## When To Prefer `sdk.knowledge`

If your actual goal is not "run extraction" but rather:

- ingest a document into knowledge storage
- resolve or materialize media-backed document paths
- enforce strict failure when no extractor exists

then the higher-level `sdk.knowledge` facade may be the better entry point.

Use `sdk.extractors` directly when you want explicit control over extractor routing and extraction output.

## `extract_with_registered(extractor_id, path=None, data=None, filename=None, mime_type=None, config=None) -> dict | None`

This method runs one installed extractor directly.

It bypasses MIME-type binding resolution and is intended for management and
test flows where the user explicitly selected the extractor to exercise.

```python
payload = module_sdk.extractors.extract_with_registered(
    extractor_id="pdf-extractor",
    path=materialized.path,
    filename="report.pdf",
    mime_type="application/pdf",
)
```

Use this for extractor detail pages, diagnostics, and runtime smoke tests.

Do not use it for normal ingestion routing. In normal document flows, call
`extract(...)` so the configured MIME binding remains the source of truth.

Failure behavior:

- returns `None` when the extractor id is missing from the registry or not
  installed/active
- raises `ValueError("extractor_id is required")` for an empty extractor id
- raises `ValueError("path or data is required")` when no input is provided
