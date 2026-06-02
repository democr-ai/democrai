# Core Model: `mcp_server_registry`

The `mcp_server_registry` core model stores MCP server definitions known to the platform.

It is one of the more operationally significant models in the domain because writes can trigger runtime side effects such as allowlist refreshes and MCP tool-cache invalidation.

## What This Model Represents

Rows include:

- `id`
- `name`
- `transport`
- `endpoint_url`
- `config`
- `enabled`
- `timeout_ms`

The `config` field is decrypted on output and encrypted on write by the model layer.

## Typical Use Cases

Use `module_sdk.models.mcp_server_registry` when you need to:

- list configured MCP servers
- create a new server registration
- update endpoint or config details
- enable or disable a server

## Listing MCP Servers

Example:

```python
listing = module_sdk.models.mcp_server_registry.list(
    page=0,
    page_size=100,
    filters={"enabled": True},
)
```

Supported filters include:

- `id`
- `name`
- `transport`
- `enabled`

## Creating A Server

Example:

```python
created = module_sdk.models.mcp_server_registry.create(
    {
        "name": "internal-docs",
        "transport": "http",
        "endpoint_url": "https://mcp.example.com",
        "config": {"api_key": "secret"},
        "enabled": True,
        "timeout_ms": 15000,
    }
)
```

### What It Validates And Does

The model:

- requires `name` to match `^[A-Za-z0-9-]+$`
- only accepts `transport="http"`
- requires `endpoint_url`
- normalizes `timeout_ms`
- encrypts config before persistence
- rejects duplicate names
- emits an OS allowlist refresh request after writes
- invalidates MCP tool cache entries

This is a strong example of why `module_sdk.models` is a business/runtime layer rather than mere CRUD sugar.

## Updating And Deleting

Example:

```python
updated = module_sdk.models.mcp_server_registry.update(
    row_id,
    {"enabled": False},
)

deleted = module_sdk.models.mcp_server_registry.delete(row_id)
```

Use these operations when you are intentionally changing the registered MCP server set and want the corresponding runtime side effects to happen.

### Important Runtime Behavior

`update(...)` always invalidates MCP tool cache entries for the current server name, and also invalidates the previous name if the row was renamed.

The OS allowlist refresh on update is triggered only when the effective runtime-relevant fields actually changed, such as:

- `transport`
- `endpoint_url`
- `config`
- `enabled`

`delete(...)` always triggers both:

- allowlist refresh
- MCP tool cache invalidation
