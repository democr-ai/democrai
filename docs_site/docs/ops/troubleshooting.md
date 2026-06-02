# Troubleshooting

## Action Not Found

- Ensure UI uses fully-qualified action name: `module.action`.
- Ensure action module is imported by package init.
- Check runtime module status: `python3 main.py module-status --json`.

## Permission Denied

- Ensure permission exists in `rbac.json`.
- Ensure `@permission_required` uses correct namespaced key.
- Verify current user permissions and role.

## YAML UI Not Rendering

- Verify `sdk.ui.load(...)` path.
- Verify component kind/fields against component docs.
- Verify component IDs are unique.

## Incremental Update Not Visible

- Verify `componentId`, `propertyName`, and `surfaceId`.
- Verify component capabilities support update type.
- Verify action returns correct effect shape.

## Agent or Tool Runtime Error

- Verify names are fully-qualified.
- Verify tool input schema validity.
- Verify tool output is JSON-serializable.
