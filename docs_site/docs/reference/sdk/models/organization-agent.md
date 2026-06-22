# Core Model: `organization_agent`

The `organization_agent` core model exposes organization-to-agent associations
through the SDK core-model proxy layer.

Use `module_sdk.models.organization_agent` when a module needs the platform's
canonical organization/agent mapping instead of maintaining a module-local
copy.

## Usage

```python
rows = module_sdk.models.organization_agent.list(
    page=0,
    page_size=50,
    filters={"organization_id": organization_id},
)
```

Build tables and forms from the model schema methods when available. The core
model owns validation, access scope, and persistence semantics.
