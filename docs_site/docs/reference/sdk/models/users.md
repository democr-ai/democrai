# Core Model: `users`

The `users` core model is the main platform-facing entry point for working with user accounts from module code.

It is one of the richest models in the domain because it supports:

- standard CRUD operations
- model-driven form schemas
- filter and table schemas
- credential verification
- access-profile lookup by username or id

If your module needs to interact with platform users rather than module-owned identities, this is the model to use.

## What This Model Represents

The serialized row shape includes fields such as:

- `id`
- `username`
- `email`
- `language`
- `role`
- `access_level`
- `organization_id`
- `created_at`

The detail representation also includes:

- `roles`

That makes `view(...)` useful not only for listings but also for user detail and edit screens.

## Typical Use Cases

Use `module_sdk.models.users` when your module needs to:

- list users for an admin table
- open a user detail or edit view
- create or update users from an admin action
- verify user credentials during login-like flows
- fetch the access profile for a username or user id
- reuse the canonical create/update form schema

The `auth` and `system` modules both rely on this model for real user-management flows.

## Listing Users

Example:

```python
listing = module_sdk.models.users.list(
    page=0,
    page_size=25,
    filters={"username": "alice"},
    sort={"field": "username", "direction": "asc"},
)
```

This is the right method for admin tables and selection dialogs.

### Supported Filters

The model accepts filters for:

- `id`
- `username`
- `email`
- `language`
- `role`
- `access_level`
- `organization_id`

Notably, `role` is not a raw user column. The model resolves it through the user-role relationship, so filtering by role name remains possible without the caller needing to understand the join logic.

## Viewing One User

Example:

```python
user = module_sdk.models.users.view(user_id)
```

Use this for detail pages, edit pages, and preloading the current values you want to display.

The detail payload includes the `roles` list, which is useful when your UI needs more than the single summary role name exposed in listing rows.

## Creating Users

Example:

```python
created = module_sdk.models.users.create(
    {
        "username": "alice",
        "email": "alice@example.com",
        "language": "en",
        "role": "manager",
        "access_level": 2,
        "password": "secret",
    }
)
```

### What It Validates

The model requires:

- `username`
- `password`

It also:

- rejects duplicate usernames
- resolves the named role when present
- hashes the password before storing it

This is why using the model is better than trying to recreate user persistence logic yourself in module code.

## Updating Users

Example:

```python
updated = module_sdk.models.users.update(
    user_id,
    {
        "email": "alice+new@example.com",
        "language": "it",
        "role": "admin",
    },
)
```

### What It Does

The model supports updating fields such as:

- `username`
- `email`
- `language`
- `access_level`
- `organization_id`
- `role`
- `password`

It also:

- rejects empty usernames
- rejects duplicate usernames
- lowercases the language value
- hashes a new password if one is provided

## Deleting Users

Example:

```python
deleted = module_sdk.models.users.delete(user_id)
```

This returns `True` when the user existed and was deleted, otherwise `False`.

## `verify(username, password)`

This is one of the model-specific methods that makes `users` different from a generic CRUD surface.

Example:

```python
is_valid = module_sdk.models.users.verify(username, password)
```

Use it when your module needs to check credentials against the core authentication store.

The `auth` module uses this in its login flow, which is the clearest real example of why this method belongs here.

## `get_info(username)` and `get_info_by_id(user_id)`

These methods return the user access profile rather than just the regular serialized row.

Examples:

```python
profile = module_sdk.models.users.get_info("alice")
profile_by_id = module_sdk.models.users.get_info_by_id(7)
```

Use them when the next step needs the access-profile view of the user rather than the normal table/detail payload.

That is common in authentication and session-building flows.

## Form Schemas

The model exposes both:

- `form_model_create()`
- `form_model_update(entity_id)`

Example:

```python
create_schema = module_sdk.models.users.form_model_create()
update_schema = module_sdk.models.users.form_model_update(user_id)
```

The create schema includes:

- username
- email
- language
- role
- access_level
- password
- confirm_password

The update schema excludes the password fields and keeps the edit surface focused on the standard account fields.

## Table And Filter Schemas

Use:

```python
table_model = module_sdk.models.users.table_model()
filters_model = module_sdk.models.users.filters_model()
```

when you want your page to stay aligned with the platform’s canonical admin representation of users.

This is a better long-term choice than manually duplicating a user table schema in a module page.

