# Core Model: `organization_mcp`

The `organization_mcp` core model exposes organization-to-MCP associations
through the SDK core-model proxy layer.

Use `module_sdk.models.organization_mcp` when module code needs to inspect or
manage MCP availability by organization using the platform-owned model
contract.

## Usage

```python
rows = module_sdk.models.organization_mcp.list(
    page=0,
    page_size=50,
    filters={"organization_id": organization_id},
)
```

Do not infer MCP access from local module state when this core model is the
source of truth.
