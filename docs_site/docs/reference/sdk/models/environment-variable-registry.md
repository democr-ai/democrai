# Core Model: `environment_variable_registry`

`environment_variable_registry` exposes managed environment-variable declarations and configuration state for table-driven UI.

It is read-only through `module_sdk.models`. Create, update, delete, encryption, process application, and multinode dispatch belong to `module_sdk.environment`.

Rows never expose decrypted values. Use `masked_value`, `has_value`, `enabled`, and `configured` for UI state.

Typical DataTable usage:

```yaml
- kind: DataTable
  id: environment_variable_table
  remote_service: system.list_environment_variables
  paginated: true
  model: []
  rows: []
```

The model only lists variables declared by module, engine, or extractor manifests. Ad-hoc names are rejected by the `environment` SDK domain.

