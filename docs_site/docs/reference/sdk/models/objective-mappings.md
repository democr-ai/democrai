# Core Model: `objective_mappings`

The `objective_mappings` core model maps a named objective to a model registry row.

Use it when your module needs to define or maintain “for objective X, use model Y” style selections.

## What This Model Represents

Rows include:

- `id`
- `objective`
- `model_id`

This model is intentionally small and specific. It exists to encode a stable mapping between an objective name and a selected model.

## Typical Use Cases

Use `module_sdk.models.objective_mappings` when you need to:

- assign a model to a named objective
- inspect existing objective routing
- update an objective to point to a different model

## Listing Objective Mappings

Example:

```python
listing = module_sdk.models.objective_mappings.list(
    page=0,
    page_size=100,
    filters={"objective": "summarization"},
)
```

Supported filters include:

- `id`
- `objective`
- `model_id`

## Creating A Mapping

Example:

```python
created = module_sdk.models.objective_mappings.create(
    {
        "objective": "summarization",
        "model_id": 12,
    }
)
```

### What It Validates

The model:

- requires `objective` and `model_id`
- rejects duplicate objective names
- verifies that the referenced `model_id` exists

This is exactly the kind of referential rule you want to keep in the model layer rather than in ad-hoc module code.

## Updating And Deleting

Example:

```python
updated = module_sdk.models.objective_mappings.update(
    row_id,
    {"model_id": 13},
)

deleted = module_sdk.models.objective_mappings.delete(row_id)
```

Use update when an objective should point to a different model without changing the objective name itself.

