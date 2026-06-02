# Decorators: Helpers and Notes

## Helper Functions

## `get_registry()`

Use this when you need access to the action registry currently exposed by the SDK.

This is mostly useful for runtime plumbing, inspection, or advanced tests. Ordinary module code usually does not need it.

### Example

```python
from democrai.sdk.decorators import get_registry

registry = get_registry()
```

## `module_sdk.decorators`

The SDK also exposes a module-scoped decorator facade as `module_sdk.decorators`.

### Why it exists

This wrapper binds the current module name and auto-qualifies registrations explicitly through the SDK facade.

In practice, most modules import decorators directly from `democrai.sdk.decorators`.

### Practical guidance

Prefer one style consistently within a module.

If the module already uses:

```python
from democrai.sdk.decorators import action, tool, agent
```

keep using that style.

If you are working in a context where the module-scoped facade is already the pattern, it is fine to use `module_sdk.decorators`.

## Practical Guidance

If you need to choose quickly:

- use `@action(...)` for interactive client-triggered module behavior
- use command decorators only for command-runtime lifecycle behavior
- use `@ui_template(...)`, `@home_page(...)`, and `@guest_page(...)` for UI/page registration
- use `@render_hook(...)` and `@render_hook_slot(...)` for render extension points
- use `@event_listener(...)` and `@event_slot(...)` for event extension points
- use `@tool(...)`, `@agent(...)`, and `@pipeline(...)` for agent runtime assets
- use `@public`, `@setup_only`, `@only_guest`, and `@template(...)` as metadata markers, not as substitutes for registry decorators

## Practical Rules

1. Treat decorators in this domain as registration contracts, not as business logic.
2. Prefer stable, module-qualified names for runtime assets.
3. Use `@action(...)` for UI-triggered server behavior, not command decorators.
4. Use fully qualified keys for render hooks and event listeners, otherwise registration is skipped.
5. Keep the difference clear between declaring a slot (`render_hook_slot`, `event_slot`) and implementing a handler (`render_hook`, `event_listener`).
6. Register only real runtime assets with `@tool`, `@agent`, and `@pipeline`; do not decorate ordinary helpers just because they exist.
7. Remember that actions are private for unauthenticated requests unless explicitly marked with `@public`; setup actions should use `@setup_only`.
