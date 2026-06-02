# Discovery And Resolution

This section covers the methods that help modules answer three questions:

1. which extractors exist?
2. which MIME types are configurable for installed extractors?
3. which extractor would be chosen for this file?

Those are different questions, and the domain exposes different methods for each.

## `list_manifests() -> list[dict]`

This method returns the extractor manifests discovered from the extractor roots on disk.

Example:

```python
manifests = module_sdk.extractors.list_manifests()
```

### What It Is For

Use this when you need the filesystem-discovered capability catalog rather than the operational registry state.

Typical use cases:

- an admin page that shows all extractor plugins discovered by the runtime
- debugging why an extractor is or is not being discovered
- tooling that wants to inspect declared file extensions, mime types, or manifest metadata

### What It Returns

The payload comes from valid `manifest.json` files found under the configured extractor roots.

In practice, each manifest can include things such as:

- `id`
- `name`
- `entrypoint`
- `file_extensions`
- `mime_types`
- `priority`
- runtime and install policy sections declared by the extractor

The manifest loader normalizes important fields such as:

- extractor id to lowercase
- file extensions to lowercase
- mime types to lowercase

### Why You Would Use It

This method tells you what the runtime can discover from disk, regardless of current registry or activation state.

That is useful because discovery problems and registry problems are not the same.

If an extractor is missing from `list_manifests()`, the issue is usually about manifest discovery or validity.

If it appears in `list_manifests()` but not where you expect operationally, the issue is probably in registration or status state, which is where `list_registered()` becomes relevant.

## `list_registered() -> list[dict]`

This method returns the extractor rows currently present in the extractor registry model.

Example:

```python
rows = module_sdk.extractors.list_registered()
```

### What It Is For

Use this when you care about operational state rather than just discovery.

Typical examples:

- show which extractors are `active`, `installed`, or `uninstalled`
- inspect registry priority and effective matching configuration
- build an admin table of extractors actually known to the runtime

### What It Returns

The method queries `module_sdk.models.extractor_registry` and returns serialized registry rows.

Those rows can include fields such as:

- `id`
- `name`
- `extractor_id`
- `config`
- `file_extensions`
- `mime_types`
- `priority`
- `status`
- `supported`

### Why This Matters

`list_manifests()` answers "what extractor manifests were found on disk?"

`list_registered()` answers "what extractor rows does the runtime currently know about operationally?"

That second question is usually the one you need for admin UI and debugging real routing behavior.

## `list_configurable_mime_bindings() -> list[dict]`

This method returns the MIME types that can be configured for extraction and the
installed extractors that support each MIME type.

Example:

```python
rows = module_sdk.extractors.list_configurable_mime_bindings()
```

Each row includes:

- `id`: the MIME type, suitable for table row ids
- `mime_type`: normalized MIME type
- `configured_extractor_id`: selected extractor id, or an empty string
- `extractor_options`: select options for compatible installed extractors
- `configured`: whether a binding currently exists

The first option is always the unconfigured state:

```python
{"label": "Not configured", "value": ""}
```

Use this method for admin/configuration pages. Do not build compatible extractor
lists in the UI by manually comparing manifest fields. The backend filters
options to extractors that are installed/active and actually declare support for
the MIME type.

## `list_ingestible_mime_types() -> list[str]`

This method returns only MIME types that currently have an extractor binding.

Example:

```python
allowed = set(module_sdk.extractors.list_ingestible_mime_types())
```

Use this as an upload filter when a feature should accept only files that can
enter the extraction/ingestion flow. If a MIME type has no binding, it is not
ingestible even if some extractor manifest declares theoretical support for it.

## `set_mime_type_binding(mime_type, extractor_id) -> dict | None`

This method sets or clears the extractor selected for one MIME type.

Example:

```python
binding = module_sdk.extractors.set_mime_type_binding(
    mime_type="application/pdf",
    extractor_id="docling",
)
```

Clear a binding by passing `None` or an empty extractor id:

```python
module_sdk.extractors.set_mime_type_binding(
    mime_type="application/pdf",
    extractor_id=None,
)
```

Validation happens server-side:

- `mime_type` is required
- the extractor must exist in the registry
- the extractor must be installed or active
- the extractor must declare support for that MIME type

On success, the method returns:

- `id`
- `mime_type`
- `extractor_id`

When a binding is cleared, the method returns `None`.

## `resolve(path=None, filename=None, mime_type=None) -> dict | None`

This method resolves the active extractor for a file-like source.

Example with path:

```python
resolved = module_sdk.extractors.resolve(
    path="documents/report.pdf",
    mime_type="application/pdf",
)
```

Example with in-memory upload metadata:

```python
resolved = module_sdk.extractors.resolve(
    filename="invoice.pdf",
    mime_type="application/pdf",
)
```

### What It Is For

Use this when your module needs to know which registered extractor would be selected before actually running extraction.

Typical reasons:

- show the user which extractor will handle a file
- debug why a file is being routed to the wrong extractor
- fail early if no registered extractor matches
- inspect the chosen extractor configuration before running it

### Resolution Inputs

The method can resolve using:

- `path`
- `filename`
- `mime_type`

If you do not pass `mime_type`, the facade will try to infer it from `path` or `filename` using `guess_mime_type(...)`.

### What The Resolver Actually Does

Under the hood, the resolver:

1. normalizes the MIME type
2. infers the MIME type from `path` or `filename` when the caller did not pass one
3. looks up the explicit MIME binding
4. verifies that the bound extractor still exists, is installed/active, and still supports that MIME type
5. returns the bound extractor payload

There is no implicit extension-priority fallback in the current contract. A
source is extractable only when its MIME type has an explicit binding.

### Return Value

On success, the method returns the resolved extractor payload.

That payload includes fields such as:

- `row_id`
- `name`
- `extractor_id`
- `config`
- `status`
- `priority`
- `file_extensions`
- `mime_types`
- `mime_match`
- `extension_match`

If no extractor matches, the method returns `None`.

### Why This Method Matters

A module should not guess extractor routing on its own by manually inspecting file extensions.

The runtime already knows:

- which extractor rows are eligible
- which ones are active
- which MIME type bindings are configured

Using `resolve(...)` keeps your routing logic aligned with the actual runtime decision.

## `resolve_for_mime_type(mime_type: str) -> dict | None`

This is a convenience wrapper around `resolve(...)` for cases where mime type is the only signal you have.

Example:

```python
resolved = module_sdk.extractors.resolve_for_mime_type("application/pdf")
```

### What It Is For

Use this when your module already has a trusted mime type and does not need path- or filename-based extension inference.

This is especially useful in flows where:

- the source is in memory
- the filename is unreliable
- mime type was already determined upstream

### Why It Exists

The method is small, but it makes intent clearer.

Calling `resolve_for_mime_type(...)` tells the next developer that mime type is the routing source of truth in this flow.

## `guess_mime_type(path_or_name: str) -> str | None`

This static helper guesses a mime type from a path or filename using Python’s `mimetypes` module.

Example:

```python
mime_type = module_sdk.extractors.guess_mime_type("report.pdf")
```

### What It Is For

Use this when you only have a filename or path and want a reasonable mime-type hint before calling `resolve(...)` or `extract(...)`.

### Important Limitation

This is only an extension-based guess.

It does not inspect file content, so it should be treated as a convenience hint rather than authoritative content detection.

### Practical Guidance

If your module already knows the actual mime type from the upload or media layer, pass it explicitly instead of relying on guessing.

That makes extractor resolution more deterministic.

## Choosing The Right Discovery Method

Use:

- `list_manifests()` when you want discovery from disk
- `list_registered()` when you want runtime registry state
- `list_configurable_mime_bindings()` when you want the admin/configuration matrix
- `list_ingestible_mime_types()` when you need an upload filter
- `set_mime_type_binding(...)` when an admin action changes the selected extractor for a MIME type
- `resolve(...)` when you want the actual extractor routing decision
- `resolve_for_mime_type(...)` when mime type is your primary signal
- `guess_mime_type(...)` only as a fallback hint
