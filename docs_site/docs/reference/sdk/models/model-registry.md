# Core Model: `model_registry`

The `model_registry` core model represents concrete models attached to installed engines.

If `available_model_registry` is the catalog-side description of what could exist, `model_registry` is the runtime-side record of a model entry that is actually associated with an engine instance.

## What This Model Represents

Rows include:

- `id`
- `name`
- `engine_id`
- `available_model_id`
- `model_path`
- `vram_required_mb`
- `ram_required_mb`
- `is_downloaded`
- `remote_url`
- `version`
- `capabilities`
- `extra_config`
- `status`

This makes the model useful both for admin inventory pages and for runtime orchestration data.

### Capability-Specific `extra_config`

`extra_config` stores runtime metadata that belongs to the registered model
binding.

For embedding models, the knowledge runtime reads:

- `extra_config.dim`: positive integer vector dimension

This value is required when the model is selected as the knowledge embedding
backend. It is model metadata, not a knowledge-global setting, because stored
embeddings and vector indexes must know which model produced vectors of which
dimension.

For chat/reasoning models, LLM parser and generation defaults may live in
`extra_config.defaults`. Do not add LLM defaults such as `temperature`, `top_p`,
or `max_tokens` to models that only expose embedding, reranking,
classification, STT, TTS, detection, or token extraction capabilities.

## Typical Use Cases

Use `module_sdk.models.model_registry` when you need to:

- list models attached to an engine
- create or update installed-model rows
- reconcile a runtime model against a catalog model
- delete stale model rows

The `system` module uses this model heavily in model registration and binding flows.

## Listing Models

Example:

```python
listing = module_sdk.models.model_registry.list(
    page=0,
    page_size=200,
    filters={"engine_id": 3, "status": "available"},
)
```

Supported filters include:

- `id`
- `name`
- `engine_id`
- `available_model_id`
- `status`
- `is_downloaded`
- `capabilities`

## Creating A Model Row

Example:

```python
created = module_sdk.models.model_registry.create(
    {
        "name": "llama3",
        "engine_id": 3,
        "model_path": "models/llama3/model.gguf",
        "capabilities": ["chat"],
        "status": "available",
    }
)
```

### What It Validates

The model:

- requires `name` and `engine_id`
- rejects duplicate model names
- verifies that `engine_id` exists
- verifies that `available_model_id` exists when provided
- normalizes capabilities into the stored CSV representation

That makes it safe for modules that need to create registry rows but do not want to reimplement foreign-key validation and payload normalization.

## Updating A Model Row

Example:

```python
updated = module_sdk.models.model_registry.update(
    row_id,
    {
        "is_downloaded": 1,
        "status": "available",
        "extra_config": {"source_mode": "artifact"},
    },
)
```

Use this when your module needs to reconcile runtime state after downloads, installs, or bindings.

## Deleting A Model Row

Example:

```python
deleted = module_sdk.models.model_registry.delete(row_id)
```

This is appropriate for removing stale registry rows, not for deleting the underlying artifact storage by itself. Storage cleanup remains a separate concern.

## Table And Filter Schemas

The model exposes canonical list metadata through `table_model()` and `filters_model()`, which is useful for admin pages and dynamic tables.
