# Core Model: `roles`

The `roles` core model is the platform-facing API for role definitions and their permission sets.

Use it when your module needs to build admin UI or actions around role management without reimplementing how the core platform stores and validates roles.

## What This Model Represents

Listing rows include:

- `id`
- `name`
- `description`
- `permissions_count`

Detail rows also include:

- `permissions`

That split is useful because the list view stays compact while the detail view still exposes the full permission set.

## Typical Use Cases

Use `module_sdk.models.roles` when you need to:

- list roles in an admin table
- inspect one role and its permissions
- create or update roles
- populate a permissions multiselect from the canonical permission list
- reuse the core form schemas for role create/update pages

## Listing Roles

Example:

```python
listing = module_sdk.models.roles.list(
    page=0,
    page_size=25,
    filters={"name": "admin"},
)
```

### Supported Filters

The model accepts:

- `id`
- `name`
- `description`
- `permission`

The `permission` filter is useful because it lets you search roles by one of their attached permission names instead of only by role metadata.

## Viewing One Role

Example:

```python
role = module_sdk.models.roles.view(role_id)
```

Use this for role detail pages and edit pages where the permission list matters.

## Creating Roles

Example:

```python
created = module_sdk.models.roles.create(
    {
        "name": "support_admin",
        "description": "Support team admin role",
        "permissions": [
            "system.user.view",
            "system.user.update",
        ],
    }
)
```

### What It Validates

The model:

- requires a non-empty role name
- rejects duplicate role names
- resolves the listed permissions
- creates missing permission records when needed

That last point is important. The role model does not just attach pre-existing permissions. It can materialize permission rows as part of the role workflow.

## Updating Roles

Example:

```python
updated = module_sdk.models.roles.update(
    role_id,
    {
        "description": "Updated description",
        "permissions": ["system.user.view"],
    },
)
```

### Important Restriction

The model explicitly blocks modification of the super role.

If you try to update a protected super role, it raises:

```text
ValueError("super role cannot be modified or deleted")
```

That is a good example of why this domain should be treated as business logic, not just persistence.

## Deleting Roles

Example:

```python
deleted = module_sdk.models.roles.delete(role_id)
```

As with update, deleting the protected super role is explicitly rejected.

## Form Schemas

The model exposes:

- `form_model_create()`
- `form_model_update(entity_id)`

Both are useful for role admin pages.

The canonical fields are:

- `name`
- `description`
- `permissions`

## `form_model_extra("permissions_options")`

This is the model-specific helper that matters most on the UI side.

Example:

```python
options = module_sdk.models.roles.form_model_extra("permissions_options")
```

It returns `{label, value}` pairs for all known permissions, ordered by permission name.

Use it to populate a permissions multiselect instead of hardcoding permission lists in module code.

The `system` module already uses this exact pattern in role create and update pages.

## Table And Filter Schemas

Use:

```python
table_model = module_sdk.models.roles.table_model()
filters_model = module_sdk.models.roles.filters_model()
```

when you want to render the canonical platform representation of roles.

