# Core Model: `extractor_mime_type_binding`

The `extractor_mime_type_binding` core model stores the explicit MIME-to-extractor routing table used by the knowledge extractor runtime.

This model is the persistence layer behind:

- `module_sdk.extractors.list_configurable_mime_bindings()`
- `module_sdk.extractors.list_ingestible_mime_types()`
- `module_sdk.extractors.set_mime_type_binding(...)`
- `module_sdk.extractors.resolve(...)`

## What This Model Represents

Rows include:

- `id`
- `mime_type`
- `extractor_id`

`mime_type` is normalized to lowercase. `extractor_id` is normalized to lowercase.

Only one binding can exist for a given MIME type.

## Boundary

Most module code should use `module_sdk.extractors` instead of manipulating this model directly.

Use the extractor SDK methods when you want validation that:

- the extractor exists
- the extractor is installed or active
- the extractor supports the selected MIME type

Direct model CRUD is useful for generic admin tables and diagnostics, but it does not replace the domain-level validation in `sdk.extractors`.

## Listing Bindings

Example:

```python
listing = module_sdk.models.extractor_mime_type_binding.list(
    page=0,
    page_size=100,
    filters={"mime_type": "application/pdf"},
)
```

Supported filters include:

- `id`
- `mime_type`
- `extractor_id`

## Creating A Binding

Example:

```python
created = module_sdk.models.extractor_mime_type_binding.create(
    {
        "mime_type": "application/pdf",
        "extractor_id": "docling",
    }
)
```

The model requires both fields and rejects duplicate MIME bindings.

For user-facing configuration actions, prefer:

```python
module_sdk.extractors.set_mime_type_binding(
    mime_type="application/pdf",
    extractor_id="docling",
)
```

That method validates extractor compatibility before writing the row.

## Updating And Deleting

Update and delete behave like ordinary core-model registry operations:

```python
updated = module_sdk.models.extractor_mime_type_binding.update(
    row_id,
    {"extractor_id": "docling"},
)
deleted = module_sdk.models.extractor_mime_type_binding.delete(row_id)
```

Deleting a row makes the MIME type non-ingestible until another extractor is configured for it.
