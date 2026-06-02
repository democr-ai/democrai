# Sessions and Metrics

This section covers the lightweight operational reporting subdomains:

- `module_sdk.system.sessions`
- `module_sdk.system.connections`
- `module_sdk.system.metrics`
- `module_sdk.system.runtime_nodes`
- `module_sdk.system.notifications`

These APIs are especially useful for dashboards and admin views that need a quick runtime snapshot without reaching into lower-level infrastructure code.

## `system.sessions.count_active() -> int`

This method returns the number of currently active sessions.

Example:

```python
active_sessions = module_sdk.system.sessions.count_active()
```

### What It Is For

Use it for:

- operational dashboards
- admin summary cards
- quick health/status screens

The `monitor` module uses exactly this kind of call for runtime stats.

### What It Actually Does

The method queries the `SessionIdentity` table.

If `session.idle_ttl_seconds` is configured with a positive integer value, it only counts sessions updated after the TTL threshold.

If the TTL is missing, empty, zero, or invalid, it falls back to counting all rows in the session identity store.

### Why This Matters

This is not “how many websocket clients are currently connected right now”.

It is “how many session identity rows count as active under the configured idle TTL policy”.

That makes it a useful operational metric, but a different one from live transport presence.

## `system.connections`

The `connections` subdomain reports live authenticated client presence from the
runtime connection registry. It does not query persisted sessions.

```python
connected_users = module_sdk.system.connections.count_active_users()
connected_clients = module_sdk.system.connections.count_active_connections()
rows = module_sdk.system.connections.list_active_users()
```

### Methods

| Method | Returns | Notes |
|---|---|---|
| `count_active_users()` | `int` | Counts connected user scopes visible to the current session. |
| `count_active_connections()` | `int` | Counts open client connections visible to the current session. |
| `list_active_users()` | `list[dict]` | Returns `user_id`, `organization_id`, and `connections` for each visible connected user scope. |

### Visibility

The result follows the current session access scope:

- super users can see all connected user scopes
- organization users can see connected users in their organization
- regular users can see only their own connected scope

Use this when you need live presence in a monitor page. Keep
`system.sessions.count_active()` for session-store reporting.

## `system.metrics.read() -> dict[str, Any]`

This method returns a point-in-time runtime resource snapshot.

Example:

```python
metrics = module_sdk.system.metrics.read()
```

The returned payload includes:

- `cpu_percent`
- `ram_total_mb`
- `ram_free_mb`
- `ram_used_mb`
- `ram_used_percent`
- `vram_total_mb`
- `vram_free_mb`
- `vram_used_mb`
- `has_nvidia_gpu`

### What It Is For

Use it when your module needs to display a lightweight operational snapshot of host resources.

Typical examples:

- monitoring dashboards
- admin status pages
- engine setup screens that need to show current RAM/VRAM context

### What It Actually Does

The method combines:

- `psutil` for CPU percent and memory percentage
- the resource monitor for GPU-aware and normalized RAM/VRAM values

If the resource monitor has explicit RAM totals/free numbers, those are used. Otherwise it falls back to the `psutil` virtual memory snapshot.

### Why This Detail Matters

This method is a convenient summary, not a full hardware inventory or time-series metric stream.

It gives you one snapshot suitable for rendering or quick operational logic.

## `system.runtime_nodes.list() -> list[dict[str, Any]]`

This method returns runtime nodes registered by the metrics publisher.

Example:

```python
nodes = module_sdk.system.runtime_nodes.list()
```

The returned rows include:

- `id`
- `node_id`
- `label`
- `status`
- `hostname`
- `has_nvidia_gpu`
- `started_at`
- `last_seen_at`
- `updated_at`
- `created_at`

### What It Is For

Use it in monitor-style UI that needs to show which runtime nodes are currently known to the application.

This is a read-only operational helper. It is not a node registration API and it does not start, stop, or supervise runtime nodes.

## `system.notifications`

The `notifications` subdomain exposes core notification state to module views.

```python
items = module_sdk.system.notifications.list()
count = module_sdk.system.notifications.count()
view_path = module_sdk.system.notifications.center_view_path()
```

### Methods

| Method | Returns | Notes |
|---|---|---|
| `list()` | `list[dict]` | Returns notifications visible to the current SDK session. |
| `count()` | `int` | Returns the current pending notification count for the session. |
| `center_view_path()` | `str` | Returns the registered notification-center route. |

### What It Is For

Use this only for notification-center surfaces and small notification badges.

The core owns the notification actions and count state. A module can provide the notification-center page, but it should read the notification list through this SDK facade instead of importing core notification helpers directly.

## Practical Guidance

These methods are ideal for dashboards precisely because they are simple.

If your module needs history, event streams, or detailed observability analysis, move into the observability and model layers instead of trying to overload `system.sessions` or `system.metrics`.
