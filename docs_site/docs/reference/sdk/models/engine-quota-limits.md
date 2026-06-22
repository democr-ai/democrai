# Core Model: `engine_quota_limits`

The `engine_quota_limits` core model stores configured engine quota limits.

Most module code should use the quota helpers on `module_sdk.engines`, because
those helpers bind scope-specific operations to the correct engine, organization,
role, or user target.

## Usage

```python
limits = module_sdk.models.engine_quota_limits.list(
    page=0,
    page_size=50,
    filters={"engine_row_id": engine_registry_id},
)
```

Use `module_sdk.engines.quota_metadata()` as the source for scope, period, and
metric constants. Do not hardcode those lists in UI code.
