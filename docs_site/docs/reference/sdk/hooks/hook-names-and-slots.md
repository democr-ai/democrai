# Hook Names And Slots

This section covers the two foundational pieces of the render-hook system:

- naming
- slot declaration

If those are not clear, everything else becomes fragile very quickly.

## Relative Names vs Fully Qualified Names

Render-hook names are treated as module-scoped contract keys.

If your module is `auth` and you talk about `login.form.after_fields`, the fully qualified hook key is usually:

```text
auth.login.form.after_fields
```

This is why the facade exposes `qualify_render_hook_name(...)`.

The slot owner often wants to work with a short relative name inside its own module, while downstream providers should target the fully qualified key explicitly.

## `qualify_render_hook_name(name: str) -> str`

This method returns the fully qualified hook name for the current module.

Example:

```python
qualified = module_sdk.hooks.qualify_render_hook_name(
    "dashboard.after_stats"
)
# -> "my_module.dashboard.after_stats"
```

### What It Is For

Use this when you need the canonical hook name rather than the short module-local form.

Typical cases:

- logging
- documenting slot contracts
- checking that provider registration is targeting the exact expected key
- generating references to hook names in config or developer tooling

### How It Works

The rule is simple:

- if the current module is `core`, the name is left unchanged
- if the name is already prefixed with the current module, the name is left unchanged
- otherwise the current module name is prefixed automatically

### Why It Matters

Without this normalization, slot owners and providers drift very easily.

One module thinks the hook is `dashboard.after_stats`, another registers `analytics.dashboard.after_stats`, and now the extension point silently stops working.

`qualify_render_hook_name(...)` keeps the slot owner side deterministic.

## `@render_hook_slot(...)` And Slot Contracts

Although the decorator is documented under the `decorators` domain, it is part of the practical `hooks` mental model and should be understood together with this facade.

A render-hook slot declares:

- the public hook key
- whether providers are optional
- a human-readable description

Example:

```python
@render_hook_slot(
    "login.form.after_fields",
    optional=True,
    description="Inject additional UI after the login form fields.",
)
def register_login_after_fields_hook():
    return None
```

If this is declared inside the `auth` module, the public slot key becomes:

```text
auth.login.form.after_fields
```

### Why Slot Declarations Matter

Slots are what turn a render hook from a hidden convention into a public extension contract.

If a slot is resolved without being declared, the runtime logs a warning that the hook was resolved without being declared as a public hook API.

That warning is telling you something real:

- undeclared hooks can still work
- declared hooks are easier to discover, document, and maintain

If a hook is meant to be extended by other modules, declare the slot.

## `get_render_hook_slots(module_name: str | None = None)`

This method returns the declared render-hook slot definitions from the runtime registry.

Example:

```python
all_slots = module_sdk.hooks.get_render_hook_slots()
auth_slots = module_sdk.hooks.get_render_hook_slots("auth")
```

### What It Is For

Use this method when your module wants to inspect which public hook slots have been declared across the application.

Typical use cases:

- developer documentation pages
- extension browser/debug screens
- validation tooling
- module admin UIs that explain available UI extension points

### What It Returns

Each slot definition contains metadata such as:

- `name`
- `module_name`
- `optional`
- `description`

This is the runtime-visible declaration of the public hook contract.

### Filtering By Module

Pass `module_name` when you only want hooks declared by a specific owner module.

Omit it when you want the full global list.

### Why This Method Is Useful

Render hooks are much easier to build against when the extension surface is inspectable.

`get_render_hook_slots(...)` is what makes that possible.

Without it, hook contracts become tribal knowledge hidden in source files.

## Safe Naming Guidance

Render-hook names work best when they describe a stable UI position owned by a specific module.

Good examples:

- `auth.login.form.after_fields`
- `crm.dashboard.after_stats`
- `billing.invoice.view.sidebar`

Weak examples:

- `extra`
- `slot1`
- `hook`

The name should tell another developer where the injected UI will appear.

