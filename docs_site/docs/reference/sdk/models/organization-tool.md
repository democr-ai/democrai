# Core Model: `organization_tool`

The `organization_tool` core model exposes organization-to-tool associations
through the SDK core-model proxy layer.

Use `module_sdk.models.organization_tool` when a module needs to work with
tool availability or assignments at organization scope.

## Usage

```python
rows = module_sdk.models.organization_tool.list(
    page=0,
    page_size=50,
    filters={"organization_id": organization_id},
)
```

Let the core model define allowed filters, schemas, and access behavior. Module
UI should consume those contracts rather than duplicating them.
