# Engine Quotas

The `engines` facade exposes synchronous helpers for engine quota administration.

These methods sit on top of the core model proxies for `engine_quota_counters`
and `engine_quota_limits`. They are part of `module_sdk.engines`, but they are
not async like the runtime/provider methods in this domain.

## Metadata

Use `quota_metadata()` before rendering forms or selectable values:

```python
metadata = module_sdk.engines.quota_metadata()
```

The returned payload contains the public quota constants:

- `metric_types`
- `period_units`
- `scope_types`
- `global_scope_types`
- `target_scope_types`

Do not hardcode quota scope or metric lists in module UI. Read them from this
method so the UI stays aligned with the central quota contract.

## Counters

Quota counters are exposed through these synchronous methods:

- `list_quota_counters(page=0, page_size=200, filters=None, sort=None)`
- `get_quota_counter(counter_id=...)`
- `create_quota_counter(payload)`
- `update_quota_counter(counter_id=..., payload=...)`
- `delete_quota_counter(counter_id=...)`

Example:

```python
counters = module_sdk.engines.list_quota_counters(
    filters={"engine_row_id": engine_registry_id},
)
```

The SDK delegates validation and persistence to the `engine_quota_counters`
core model. Module code should treat the payload shape as the core model
contract, not as a local UI contract.

## Global Engine Limits

Global engine limits cover the engine-level scopes returned by
`quota_metadata()["global_scope_types"]`.

Methods:

- `list_engine_global_quota_limits(engine_registry_id=..., page=0, page_size=200)`
- `create_engine_global_quota_limit(engine_registry_id=..., payload=...)`
- `update_engine_global_quota_limit(limit_id=..., engine_registry_id=..., payload=...)`

The create/update helpers enforce that the scope type belongs to the global
scope set and bind the limit to the supplied `engine_registry_id`.

## Organization, Role, and User Limits

Targeted limits are grouped by target identity:

- `list_organization_engine_quota_limits(organization_id=..., page=0, page_size=200)`
- `list_role_engine_quota_limits(role_id=..., page=0, page_size=200)`
- `list_user_engine_quota_limits(user_id=..., page=0, page_size=200)`
- `create_organization_engine_quota_limit(organization_id=..., payload=...)`
- `create_role_engine_quota_limit(role_id=..., payload=...)`
- `create_user_engine_quota_limit(user_id=..., payload=...)`
- `update_organization_engine_quota_limit(organization_id=..., limit_id=..., payload=...)`
- `update_role_engine_quota_limit(role_id=..., limit_id=..., payload=...)`
- `update_user_engine_quota_limit(user_id=..., limit_id=..., payload=...)`

These helpers set or verify the target scope from the method name. For example,
`create_user_engine_quota_limit(...)` creates a `user`-scoped limit for the
given `user_id`.

## Shared Limit Helpers

Two helpers operate on any engine quota limit by id:

- `get_engine_quota_limit(limit_id=...)`
- `delete_engine_quota_limit(limit_id=...)`

Use them when the UI already has a concrete quota limit id and does not need to
branch by scope first.

## Practical Guidance

- Use `quota_metadata()` as the source for quota constants.
- Use these facade methods instead of writing directly to quota tables.
- Keep quota forms bound to the core model payload shape.
- Do not infer engine identity from catalog model ids; quota limits bind to
  configured engine registry rows.
