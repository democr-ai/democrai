# Core Model: `audit_events`

The `audit_events` core model exposes audit log entries from the observability store.

It is a read-only model designed for inspection, filtering, and monitoring.

## What This Model Represents

Rows include:

- `id`
- `timestamp`
- `event_type`
- `actor_user_id`
- `entity_type`
- `entity_id`
- `operation`
- `status`

Detail rows also include:

- `actor_role`
- `organization_id`
- `session_id`
- `node_id`
- `request_id`
- `correlation_id`
- `client_ip`
- `channel`

## Typical Use Cases

Use `module_sdk.models.audit_events` when you need to:

- build audit dashboards
- list security or admin events
- drill into one audit record for troubleshooting

The `monitor` module uses its schema in audit tables.

## Access Scope

This model overrides the generic access-scope behavior.

In practice:

- super-level access can see everything
- organization-level access is scoped by `organization_id`
- lower-level access is scoped to rows where `actor_user_id` matches the current user

That is a good example of why the model layer is the correct place for access semantics.

## Listing Audit Events

Example:

```python
listing = module_sdk.models.audit_events.list(
    page=0,
    page_size=50,
    filters={"event_type": "auth.login"},
)
```

Supported filters include:

- `event_type`
- `actor_user_id`
- `entity_type`
- `entity_id`
- `operation`
- `status`

The default sort is `timestamp desc`.

## Viewing One Audit Event

Example:

```python
event = module_sdk.models.audit_events.view(event_id)
```

Use this when the detail metadata matters more than the list row.

## Write Operations Are Disabled

This model is read-only through the SDK. Audit data is produced by core runtime instrumentation and should not be mutated as ordinary CRUD data. Modules should not write audit events directly.

