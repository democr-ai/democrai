# Core Model: `extractor_registry`

The `extractor_registry` core model represents registered extractors and their matching rules.

If your module needs to manage which extractors exist, how they match files, and what their runtime metadata looks like, this is the model to use.

## What This Model Represents

Rows include fields such as:

- `id`
- `name`
- `extractor_id`
- `config`
- `file_extensions`
- `mime_types`
- `priority`
- `status`
- `supported`

This is the registry-level representation of extractors, not the execution API itself. Extraction execution belongs to `sdk.extractors`.

Extractor MIME routing is not derived directly from these rows at call time.
The active routing decision is stored in `extractor_mime_type_binding` and
managed through `sdk.extractors.set_mime_type_binding(...)`.

`extractor_registry.mime_types` defines what an extractor can support.
`extractor_mime_type_binding` defines which extractor is currently selected for
a MIME type.

## Typical Use Cases

Use `module_sdk.models.extractor_registry` when you need to:

- list available extractors
- register a new extractor row
- update matching rules or status
- manage extractor support metadata

## Listing Extractors

Example:

```python
listing = module_sdk.models.extractor_registry.list(
    page=0,
    page_size=100,
    filters={"status": "installed"},
)
```

Supported filters include:

- `id`
- `name`
- `extractor_id`
- `status`
- `supported`

## Creating An Extractor Row

Example:

```python
created = module_sdk.models.extractor_registry.create(
    {
        "name": "docling_pdf",
        "extractor_id": "docling",
        "file_extensions": [".pdf"],
        "mime_types": ["application/pdf"],
        "priority": 10,
        "status": "installed",
        "supported": True,
    }
)
```

### What It Validates

The model:

- requires `name` and `extractor_id`
- rejects duplicate extractor names
- requires `config` to be an object when provided
- requires `file_extensions` and `mime_types` to be lists when provided

## Updating And Deleting

Update and delete behave like ordinary core-model registry operations:

```python
updated = module_sdk.models.extractor_registry.update(row_id, {"priority": 20})
deleted = module_sdk.models.extractor_registry.delete(row_id)
```

Use them when maintaining registry metadata, not when you actually want to run extraction work.
