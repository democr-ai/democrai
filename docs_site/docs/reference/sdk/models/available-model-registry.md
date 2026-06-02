# Core Model: `available_model_registry`

The `available_model_registry` core model represents model definitions that are available to the platform catalog, regardless of whether they are already attached to a specific engine instance.

This is the model you use when you are managing the catalog-side inventory of models.

## What This Model Represents

Rows include a rich catalog-style payload with fields such as:

- `id`
- `name`
- `label`
- `catalog_model_id`
- `source_kind`
- `provider_hint`
- `format`
- `family`
- `summary`
- `storage_ref`
- `remote_url`
- `version`
- `capabilities`
- `extended_capabilities`
- `interfaces`
- `tags`
- `requirements`
- `artifacts`
- `metadata`
- `source_payload`
- `extra_config`
- `status`

This is intentionally broader than `model_registry`, because catalog entries describe what a model is and where it comes from, not just where one installed copy lives.

## Typical Use Cases

Use `module_sdk.models.available_model_registry` when you need to:

- maintain a catalog of available models
- create manual or imported catalog entries
- attach catalog metadata such as tags, interfaces, requirements, or artifacts
- build inventory pages for model discovery and selection

## Listing Catalog Entries

Example:

```python
listing = module_sdk.models.available_model_registry.list(
    page=0,
    page_size=100,
    filters={"status": "available", "format": "gguf"},
)
```

Supported filters include:

- `id`
- `name`
- `label`
- `catalog_model_id`
- `source_kind`
- `provider_hint`
- `format`
- `status`
- `capabilities`

## Creating A Catalog Entry

Example:

```python
created = module_sdk.models.available_model_registry.create(
    {
        "name": "tiny-embed",
        "label": "Tiny Embed",
        "source_kind": "manual",
        "provider_hint": "sentence-transformers",
        "format": "onnx",
        "capabilities": ["embedding"],
        "status": "available",
    }
)
```

### What It Validates

The model requires:

- `name`
- `label`

It also rejects duplicate names and normalizes the CSV-like list fields such as:

- `capabilities`
- `extended_capabilities`
- `interfaces`
- `tags`

## Updating A Catalog Entry

Example:

```python
updated = module_sdk.models.available_model_registry.update(
    row_id,
    {
        "summary": "Small embedding model",
        "metadata": {"license": "apache-2.0"},
        "artifacts": [{"id": "main"}],
    },
)
```

This is the right method for enriching a catalog entry over time as more metadata becomes available.

## Deleting A Catalog Entry

Example:

```python
deleted = module_sdk.models.available_model_registry.delete(row_id)
```

Use this when the catalog row itself should disappear. If other registry rows depend on it semantically, your module still needs to reason about those relationships at the flow level.

## Why This Model Matters

This model is the one to use when the user-facing task is “manage what models are available to the platform”, not “manage one installed model row”.

That distinction becomes important as soon as your module starts handling imports, catalogs, or provider-fed model inventories.
