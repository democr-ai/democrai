# SDK Domain: `database`

## Purpose

`sdk.database` is the persistence domain for **module-owned data**.

Use it when the data belongs to the module itself and should live in tables that are owned, shaped, and maintained by that module.

That distinction matters because this project has two different persistence surfaces:

- `sdk.database` for module-owned SQLAlchemy tables
- `sdk.models` for core-owned application entities that the platform already exposes through model-driven APIs

If you are storing records that are part of your module's own lifecycle, schema, and business logic, `sdk.database` is the right tool.

If you are reading or mutating core entities such as users, roles, engine registries, model registries, and other platform-managed data, those belong to `sdk.models`, not here.

## Mental Model

The easiest way to think about `sdk.database` is this:

- it is a module-scoped datastore
- it validates that the model belongs to the current module
- it applies access scope automatically on reads
- it assigns `user_id` and `organization_id` automatically on writes when the model exposes those fields

So this domain is not just "a CRUD helper".

It is a guarded persistence boundary that keeps modules inside their own tables and inside the current access scope.

## In This Section

- [Models and Scope](models-and-scope.md)
- [CRUD Operations](crud-operations.md)
- [Advanced Notes](advanced-notes.md)
