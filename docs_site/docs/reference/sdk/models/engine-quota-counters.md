# Core Model: `engine_quota_counters`

The `engine_quota_counters` core model stores engine quota usage counters.

Most module code should access counters through
`module_sdk.engines.list_quota_counters(...)` and related quota helpers. Use
the core model proxy directly only when you specifically need the generic model
schema methods such as `table_model()` or `filters_model()`.

## Usage

```python
counters = module_sdk.models.engine_quota_counters.list(
    page=0,
    page_size=50,
    filters={"engine_row_id": engine_registry_id},
)
```

Counters are operational quota state. Avoid writing ad-hoc module logic that
recomputes or reinterprets quota accounting outside the central quota contract.
