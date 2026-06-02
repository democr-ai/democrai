# Core Model: `engine_node_install_registry`

The `engine_node_install_registry` core model exposes per-node install status for engines.

This model is read-only from the SDK perspective. It exists so modules can inspect installation progress and history, not to mutate the installation state directly.

## What This Model Represents

Rows include fields such as:

- `id`
- `engine_id`
- `node_id`
- `status`
- `last_event_id`
- `last_error`
- `manifest_version`
- install timestamps
- heartbeat/update timestamps

This is operational runtime data, not configuration data.

## What It Is For

Use `module_sdk.models.engine_node_install_registry` when you need to:

- show engine install progress per node
- inspect installation failures
- build runtime monitoring pages
- correlate node state with higher-level engine lifecycle flows

The `system` module uses it to surface installation state in engine pages.

## Listing Install Rows

Example:

```python
listing = module_sdk.models.engine_node_install_registry.list(
    page=0,
    page_size=200,
    filters={"engine_id": "ollama"},
)
```

Supported filters include:

- `id`
- `engine_id`
- `node_id`
- `status`
- `last_event_id`

The default sort is `updated_at desc`, which is a good fit for operational monitoring because the most recent state appears first.

## Viewing One Row

Example:

```python
row = module_sdk.models.engine_node_install_registry.view(row_id)
```

Use this when a detail page needs the full install-timeline context for one node row.

## Write Operations Are Intentionally Disabled

This model is read-only.

That means:

- `create(...)` raises `NotImplementedError("engine_node_install_registry is read-only")`
- `update(...)` raises the same kind of error
- `delete(...)` raises the same kind of error

This is deliberate. Installation state is runtime-owned, not something module code should patch as ordinary CRUD data.

