# Core Model: `module_locks`

The `module_locks` core model is the platform surface for lock rules that restrict module access by user, organization, or role.

If your module needs to inspect or maintain those lock rows, this is the official model to use.

## What This Model Represents

Rows include:

- `id`
- `module_name`
- `user_id`
- `organization_id`
- `role_id`
- `created_at`
- `updated_at`

These rows are effectively policy mappings: they do not store content, they store who a lock applies to.

## Typical Use Cases

Use `module_sdk.models.module_locks` when you need to:

- list current locks for a module
- create a new lock targeting a user, organization, or role
- remove a lock row
- build a module-access admin screen

The `system` module uses it for user/module access management flows.

## Listing Locks

Example:

```python
listing = module_sdk.models.module_locks.list(
    page=0,
    page_size=200,
    filters={"module_name": "chat"},
)
```

Supported filters include:

- `id`
- `module_name`
- `user_id`
- `organization_id`
- `role_id`

## Creating A Lock

Example:

```python
created = module_sdk.models.module_locks.create(
    {
        "module_name": "chat",
        "organization_id": 7,
    }
)
```

### What It Validates

The model:

- requires `module_name`
- requires at least one of `user_id`, `organization_id`, or `role_id`

That contract is useful because it stops you from creating meaningless “empty scope” lock rows.

## Updating And Deleting Locks

Update and delete behave like normal core-model write operations:

```python
updated = module_sdk.models.module_locks.update(lock_id, {"role_id": 3})
deleted = module_sdk.models.module_locks.delete(lock_id)
```

This is a good fit for admin flows where locks are edited as rows rather than generated indirectly.

## Table And Filter Schemas

The model exposes both:

- `filters_model()`
- `table_model()`

Use them if your UI wants to stay aligned with the canonical lock representation.

