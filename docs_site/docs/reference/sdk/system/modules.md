# Modules

This section covers the `module_sdk.system.modules` subdomain:

- `list()`
- `list_active_for_user(user_id=None)`

This subdomain is about module inventory and visibility, not module loading or execution.

## What This Subdomain Represents

`module_sdk.system.modules` gives module authors a read-only view of installed modules and one convenience filter for “active for this user”.

The returned module metadata includes:

- `module_name`
- `label`
- `version`
- `icon`
- `description`

That makes it especially useful for dashboards, launchers, or admin pages that need to render the current module catalog.

## `list() -> list[dict[str, Any]]`

This method returns metadata for all installed modules known to the runtime.

Example:

```python
modules = module_sdk.system.modules.list()
```

### What It Is For

Use it when your module needs to render a general module inventory without applying user-specific visibility rules.

### What It Actually Does

The method:

1. reads `app_ctx().modules`
2. returns `[]` if no module manager is available
3. fetches all modules from `get_all_modules()`
4. sorts them by lowercased label, then by module name
5. serializes a compact metadata payload for each one

That sort order matters because it means the returned list is already presentation-friendly for most UI uses.

## `list_active_for_user(user_id=None) -> list[dict[str, Any]]`

This method returns the modules that are not explicitly locked for a specific user.

Example:

```python
active_modules = module_sdk.system.modules.list_active_for_user()
```

Example with an explicit user:

```python
active_modules = module_sdk.system.modules.list_active_for_user(user_id=8)
```

### What It Is For

Use it when the UI should show the modules the current user can still access in the simple user-specific lock case.

The dashboard module uses exactly this method when rendering the user’s module cards.

### How User Resolution Works

If `user_id` is omitted, the method tries to read the current session user id. If that still cannot be resolved, it falls back to `0`.

That means the method is designed to be convenient for session-bound UI code.

### What It Actually Checks

The method resolves the current module-access identity from the SDK session and optional `user_id`, then checks each installed module with the runtime module-lock helper.

That check includes the identity fields the helper understands, including:

- user id
- organization id
- role

The result is the installed module list minus modules explicitly locked for that resolved identity.

### Why This Detail Matters

The name `list_active_for_user(...)` is useful, but the behavior is still about module locks, not the whole authorization system.

That means it is a good fit for dashboard-style visibility filtering, but you should not document it as a universal “can this user access this module under every policy?” API.

## Practical Guidance

Use:

- `list()` when you want the installed module inventory
- `list_active_for_user()` when you want a user-facing visible list that respects module locks for the resolved identity

If your use case needs full authorization semantics, rely on the dedicated access-control flows rather than assuming this helper is the final source of truth.
