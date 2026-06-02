# Core Model: `extractor_node_install_registry`

The `extractor_node_install_registry` core model exposes per-node install state for extractors.

Like `engine_node_install_registry`, this is an operational read model rather than a writable configuration surface.

## What This Model Represents

Rows include:

- `id`
- `extractor_id`
- `node_id`
- `status`
- `last_event_id`
- `last_error`
- `manifest_version`
- install timestamps
- heartbeat/update timestamps

## What It Is For

Use `module_sdk.models.extractor_node_install_registry` when you need to:

- inspect extractor installation state across nodes
- show installation progress or errors
- build operational monitoring screens

## Listing Rows

Example:

```python
listing = module_sdk.models.extractor_node_install_registry.list(
    page=0,
    page_size=200,
    filters={"extractor_id": "docling"},
)
```

Supported filters include:

- `id`
- `extractor_id`
- `node_id`
- `status`
- `last_event_id`

The default sort is `updated_at desc`, which makes sense for monitoring views.

## Write Operations Are Disabled

This model is read-only.

That means:

- `create(...)` raises `NotImplementedError`
- `update(...)` raises `NotImplementedError`
- `delete(...)` raises `NotImplementedError`

Use higher-level extractor installation flows when you need to change runtime state.

