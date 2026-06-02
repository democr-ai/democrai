# Database: Advanced Notes

## Advanced Attributes Through Delegation

The `Database` facade delegates unknown attributes to the underlying scoped datastore through `__getattr__`.

In practice, the most useful delegated attributes in ordinary module code are:

- `module_sdk.database.user_id`
- `module_sdk.database.organization_id`
- `module_sdk.database.access_level`

You can see this pattern in the components ORM examples:

```python
notes = sdk.database.list(Note, owner=sdk.database.user_id)
settings = sdk.database.list(OrgSetting, organization_id=sdk.database.organization_id)
```

Use this sparingly and intentionally. These values are useful when your module's own schema has business fields that need to align with the active datastore actor context.

They are not a reason to manually reimplement the datastore's built-in scope rules.

## Practical Guidance

If you need to choose quickly:

- declare module-owned models from `democrai.sdk.database.Base`
- use `add(...)` to create rows
- use `get(...)` for one id-addressable row
- use `list(...)` or `all(...)` for multiple filtered rows
- use `update(...)` for one scoped row mutation
- use `delete(...)` for one scoped row removal
- use `sdk.models` instead when the data is platform-owned rather than module-owned

## Practical Rules

1. Always declare module-owned ORM models from `democrai.sdk.database.Base`.
2. Do not use `sdk.database` for core-owned tables or platform registries.
3. Rely on the datastore for module validation and scope enforcement instead of reimplementing those checks manually.
4. Do not manually set `user_id` and `organization_id` on create unless you have a very specific advanced reason and understand the overwrite behavior.
5. Treat `None` from `get(...)` and `update(...)`, and `False` from `delete(...)`, as normal scoped outcomes rather than proof of a runtime bug.
6. Prefer the simplest CRUD method that matches the job before reaching for lower-level datastore behavior.

