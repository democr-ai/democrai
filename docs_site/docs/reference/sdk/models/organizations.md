# Core Model: `organizations`

The `organizations` core model exposes application organizations through the
SDK core-model proxy layer.

Use `module_sdk.models.organizations` when module UI needs to list, view, or
otherwise work with organization records under the access rules enforced by the
core model registry.

## Usage

```python
organizations = module_sdk.models.organizations.list(page=0, page_size=50)
```

Use the model's own `filters_model()`, `table_model()`, `form_model_create()`,
and `form_model_update()` methods when building UI from schemas.

Do not duplicate organization schema, access rules, or persistence behavior in
module-local code.
