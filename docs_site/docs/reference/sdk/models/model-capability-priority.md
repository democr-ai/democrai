# Core Model: `model_capability_priority`

The `model_capability_priority` core model stores priority ordering for models within a given capability.

If your runtime needs to decide which model should win for a capability such as `chat` or `embedding`, this registry is one of the pieces that expresses that preference.

## What This Model Represents

Rows include:

- `id`
- `capability`
- `model_id`
- `priority`

This is a small model, but it carries important selection semantics.

## Typical Use Cases

Use `module_sdk.models.model_capability_priority` when you need to:

- assign a model to a capability priority slot
- reorder model priorities for a capability
- inspect which model currently has precedence

The `system` module uses it in capability-priority admin flows.

## Listing Priority Rows

Example:

```python
listing = module_sdk.models.model_capability_priority.list(
    page=0,
    page_size=200,
    filters={"capability": "chat"},
)
```

Supported filters include:

- `id`
- `capability`
- `model_id`
- `priority`

## Creating A Priority Mapping

Example:

```python
created = module_sdk.models.model_capability_priority.create(
    {
        "capability": "chat",
        "model_id": 12,
        "priority": 1,
    }
)
```

### What It Validates

The model:

- requires `capability`, `model_id`, and `priority`
- lowercases and normalizes the capability name
- requires `priority >= 1`
- verifies that `model_id` exists
- rejects duplicate `(capability, model_id)` pairs
- rejects duplicate priority values within the same capability

That last rule is important because it means a capability has an ordered, conflict-free priority list rather than a loose set of preferences.

## Updating Priority Rows

Example:

```python
updated = module_sdk.models.model_capability_priority.update(
    row_id,
    {"priority": 2},
)
```

Use this when reordering capability precedence.

## Deleting Priority Rows

Example:

```python
deleted = module_sdk.models.model_capability_priority.delete(row_id)
```

This is appropriate when removing a model from the capability-priority ordering entirely.
