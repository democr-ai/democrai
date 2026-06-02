# SDK Domain: `models`

## Overview

The `models` domain is the SDK surface modules use when they need to work with core-managed entities instead of module-owned tables.

This distinction matters.

If the data belongs to your module, `module_sdk.database` is usually the right tool.

If the data belongs to the application core and already has an official model layer with access rules, filters, table schemas, and form schemas, `module_sdk.models` is the right entry point.

That means `module_sdk.models` is not a generic ORM and it is not a raw database escape hatch. It is a proxy layer over the core model registry.

## Mental Model

When you write:

```python
module_sdk.models.users
```

you are not receiving a SQLAlchemy model and you are not receiving a plain repository object.

You are receiving a lazy proxy that will:

1. capture the current SDK session context
2. build a `CoreModelContext`
3. resolve the named core model through the core registry
4. call the selected method on that model

That context contains:

- `user_id`
- `organization_id`
- `access_level`
- `module_name`
- the full session payload
- the `bypass` flag when bypass policy is allowed

So the normal way to use this domain is not “construct context manually”, but simply “call the model proxy and let the SDK bind the current request identity for you”.

## What This Domain Is For

Use `module_sdk.models` when your module needs to work with application-owned entities such as:

- users and roles
- module locks
- engine, extractor, and model registries
- MCP server registrations
- observability data such as background tasks, audit events, and LLM usage

One of the biggest advantages of this domain is that the core model often exposes more than CRUD:

- `filters_model()` for allowed filter definitions
- `table_model()` for table schemas
- `form_model_create()` and `form_model_update()` for form generation
- model-specific methods such as `users.verify(...)` or `roles.form_model_extra(...)`

That makes it especially useful when you are building module pages that should stay aligned with the platform’s canonical representation of a core entity.

## Current Registered Core Models

At the moment, the core registry exposes these model names:

- `users`
- `roles`
- `module_locks`
- `engine_registry`
- `engine_node_install_registry`
- `environment_variable_registry`
- `model_registry`
- `available_model_registry`
- `model_capability_priority`
- `objective_mappings`
- `extractor_registry`
- `extractor_mime_type_binding`
- `extractor_node_install_registry`
- `mcp_server_registry`
- `background_tasks`
- `audit_events`
- `ai_model_usage`
- `ai_model_pipeline_steps`

The sidebar breaks these out into dedicated pages so each model can be explained in its own context.

## Important Boundary: `models` vs `database`

Use `module_sdk.models` when:

- the entity is owned by the core platform
- the model already defines access scope, filters, schemas, and serialization
- you want to stay aligned with the platform contract

Use `module_sdk.database` when:

- the table belongs to your module
- the schema is module-defined
- the lifecycle is fully under module control

If you ignore this distinction, you usually end up duplicating platform behavior or bypassing access rules the runtime already knows how to enforce.

## Subsections

- Working With Core Model Proxies
- one page for each registered core model
