# Access: Permissions and Resource Types

## Resource Types

The domain exposes these constants:

- `sdk.access.EXTERNAL_RESOURCE_NETWORK`
- `sdk.access.EXTERNAL_RESOURCE_FILESYSTEM`
- `sdk.access.EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY`

Use them instead of hardcoding strings. They are the resource-type part of the access-policy contract.

Every external-resource check also requires an `operation`.

| Resource type | Operations |
| --- | --- |
| `EXTERNAL_RESOURCE_NETWORK` | `connect`, `receive`, `send` |
| `EXTERNAL_RESOURCE_FILESYSTEM` | `read`, `create`, `modify`, `delete`, `execute` |
| `EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY` | `execute` |

`url` is not a resource type. A URL is a network target.

These resource checks exist because Democr.ai treats modules as sandbox-aware runtime code, not as fully trusted application internals. A module may be allowed to render UI and run normal business logic, but access to resources outside that boundary must still be explicit.

That is why external access is modeled separately from normal permission checks:

- a permission such as `reports.export` says what a user is allowed to do inside the product
- an external access approval says whether the module may touch a concrete outside resource

Without that distinction, any module with ordinary execution privileges could silently reach arbitrary URLs, inspect filesystem paths, or depend on undeclared system tools. The access request flow exists to make those boundaries visible, reviewable, and enforceable.

Example:

```python
sdk.access.EXTERNAL_RESOURCE_NETWORK
sdk.access.EXTERNAL_RESOURCE_FILESYSTEM
sdk.access.EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY
```

## `check_permissions(required_permissions, user_permissions) -> bool`

This is the simplest method in the domain. It answers:

"Given the permissions required by this operation, and the permissions the user actually has, should the operation be allowed?"

Use it when you already have the permission lists in hand and you just need a boolean.

Typical cases:

- validating a button action before running it
- gating a branch in module logic
- deciding whether to show or hide a dangerous operation

Example:

```python
required = ["reports.export"]
user_permissions = session.get("user", {}).get("permissions", [])

if not sdk.access.check_permissions(required, user_permissions):
    raise PermissionError("Missing reports.export")
```

This method is intentionally small. It does not inspect session state for you, and it does not know anything about external resources. It just compares required permissions with user permissions.
