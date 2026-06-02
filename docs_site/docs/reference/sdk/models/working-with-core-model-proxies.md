# Working With Core Model Proxies

This page documents the common behavior shared by all entries under `module_sdk.models`.

That shared behavior is the part you need to understand before the individual model pages start making sense.

## How Resolution Works

`module_sdk.models` is implemented as a lazy namespace.

When you access:

```python
module_sdk.models.users
```

the SDK creates a `_CoreModelProxy` for the name `users`.

That proxy does not validate the name immediately against the registry. The actual lookup happens when you invoke a method such as `list(...)`, `view(...)`, or `table_model(...)`.

This detail matters because:

- `module_sdk.models.some_typo` will still give you a proxy object
- the real failure happens later when the proxy tries to build the underlying core model
- in that case the registry raises `KeyError("Unknown core model: ...")`

So if a model name does not exist, the failure is runtime resolution, not attribute creation.

## Session Context Binding

Every method call rebuilds a `CoreModelContext` from the current SDK session.

That context includes:

- `user_id`
- `organization_id`
- `access_level`
- `module_name`
- `session`
- `bypass`

Example:

```python
listing = module_sdk.models.users.list(
    page=0,
    page_size=25,
    filters={"username": "alice"},
)
```

In this call, the proxy automatically passes the current session identity to the `users` core model. You do not need to manually inject actor information.

## Common Methods

The proxy exposes only a small allowed method surface:

- `view(...)`
- `count(...)`
- `all(...)`
- `list(...)`
- `create(...)`
- `update(...)`
- `delete(...)`
- `verify(...)`
- `get_info(...)`
- `get_info_by_id(...)`
- `form_model_create(...)`
- `form_model_update(...)`
- `form_model_extra(...)`
- `filters_model(...)`
- `table_model(...)`

Not every core model implements every method in a meaningful way.

For example:

- `users` implements `verify(...)`
- `roles` implements `form_model_extra(...)`
- several observability and install-registry models are read-only and deliberately raise `NotImplementedError` on writes

That means the proxy surface is shared, but the useful subset depends on the selected model.

There is an important practical consequence:

- if the selected model deliberately makes a write path read-only, you get `NotImplementedError`
- if you call a model-specific method that the resolved core model does not actually implement, the call can fail with `AttributeError`

So the proxy surface is broader than the guaranteed method set of every individual model.

## `view(entity_id, policy="enforced")`

Use this when you need the detailed representation of one row by id.

Example:

```python
user = module_sdk.models.users.view(user_id)
```

This usually returns either:

- a serialized detail dictionary
- or `None` if the row is missing or outside the current access scope

Many pages in the `system` module use this pattern for detail and edit views.

## `count(filters=None, policy="enforced")`

Use this when you need an access-scoped count without retrieving the rows themselves.

Example:

```python
completed = module_sdk.models.background_tasks.count(
    filters={"status": "completed"}
)
```

This is especially useful for dashboards, counters, and summary cards.

## `list(page=0, page_size=25, filters=None, sort=None, policy="enforced")`

This is the standard paginated listing method.

Example:

```python
listing = module_sdk.models.roles.list(
    page=0,
    page_size=25,
    filters={"name": "admin"},
    sort={"field": "name", "direction": "asc"},
)
```

### What It Returns

The common return shape is:

```python
{
    "rows": [...],
    "total_rows": 0,
    "page": 0,
    "page_size": 25,
    "filters": {...},
    "sort": {...},
}
```

### Important Filter Behavior

Filters are not passed through blindly.

The base core model only keeps filter keys declared by `filters_model()`. Unknown keys are dropped. Empty strings and `None` values are also ignored.

That means `list(...)` is intentionally safer than a raw query interface.

### Important Sort Behavior

Sort is also normalized against `table_model()`.

If the requested sort field is not declared as a table field, the core model falls back to its default sort.

So `sort` is best understood as a request, not an unrestricted order-by clause.

## `all(filters=None, sort=None, policy="enforced")`

Use this when you need the same core-model filtering and sorting behavior as `list(...)`, but without pagination.

Example:

```python
rows = module_sdk.models.available_model_registry.all(
    filters={"status": "available"}
)
```

The common return shape is:

```python
{
    "rows": [...],
    "filters": {...},
    "sort": {...},
}
```

This is useful for:

- loading option lists
- building derived maps in memory
- syncing or reconciling registry state

## `create(payload, policy="enforced")`, `update(entity_id, payload, policy="enforced")`, `delete(entity_id, policy="enforced")`

These are model-driven write methods for the core entities that support writes.

Example:

```python
created = module_sdk.models.available_model_registry.create(
    {
        "name": "my-model",
        "label": "My Model",
        "source_kind": "manual",
        "status": "available",
    }
)
```

You should treat these as domain operations, not raw persistence calls. The underlying core model may:

- validate uniqueness
- normalize payload fields
- encrypt sensitive config
- ensure foreign keys exist
- trigger runtime side effects after commit

This is why bypassing these models with direct writes is usually the wrong choice.

For read-only models, these methods are present on the proxy but intentionally fail with `NotImplementedError`.

## `filters_model()` and `table_model()`

These methods are one of the biggest reasons to use `module_sdk.models`.

They give you the canonical filter schema and the canonical table schema for the entity.

Example:

```python
table_model = module_sdk.models.roles.table_model()
filters_model = module_sdk.models.roles.filters_model()
```

Use them when you want your UI to stay aligned with the core model contract instead of hardcoding duplicated field declarations.

## `form_model_create()`, `form_model_update(entity_id)`, `form_model_extra(name)`

These methods are available only when the selected core model actually exposes form schemas or additional form helpers.

Examples:

```python
create_schema = module_sdk.models.users.form_model_create()
update_schema = module_sdk.models.users.form_model_update(user_id)
permission_options = module_sdk.models.roles.form_model_extra("permissions_options")
```

This is especially useful for admin pages where the platform already knows the expected input shape.

## Policy: `enforced` vs `bypass`

Most methods accept `policy`.

The normal value is:

```python
policy="enforced"
```

This is what module authors should use by default.

If you pass:

```python
policy="bypass"
```

the proxy will only allow it when:

- the session contains `_models_bypass`
- or the application is in `setup_mode`

Otherwise it raises:

```text
PermissionError("models bypass policy denied")
```

So bypass is not a convenience flag. It is a privileged runtime path.

## Access Scope

Even before model-specific filters are applied, the base model layer can scope the query according to the current access level.

In broad terms:

- super-level access sees everything
- organization-level access is scoped by `organization_id` when the model has that field
- user-level access is scoped by `user_id` when the model has that field

Some models override this logic with more specific behavior, especially observability models.

This is why the domain should be treated as the source of truth for access semantics, not just for storage.

