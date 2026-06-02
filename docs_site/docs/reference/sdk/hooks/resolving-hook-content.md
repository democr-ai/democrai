# Resolving Hook Content

This section covers the main runtime method of the domain:

- `resolve_render_hook(...)`

This is the method slot owners call inside their render flow to collect the components contributed by registered provider modules.

## `resolve_render_hook(name: str, params: dict | None = None, session: dict | None = None)`

This method resolves the components contributed to a render hook and returns the normalized component list.

Example:

```python
extra_widgets = await module_sdk.hooks.resolve_render_hook(
    "dashboard.after_stats",
    params={"workspace_id": 7},
    session=session,
)
```

## What It Is For

Use this inside a render function when your page owns a declared slot and wants to insert any contributed UI fragments into the layout.

Typical examples:

- extra fields in a form
- widgets injected below a dashboard summary
- extension cards in a sidebar
- additional sections in a settings page

## What It Actually Does

The facade:

1. qualifies the hook name using the current module prefix
2. forwards the qualified key to the render-hook runtime
3. passes through `params` and `session`
4. returns the normalized list of contributed components

So if the current module is `auth`, this call:

```python
await module_sdk.hooks.resolve_render_hook("login.form.after_fields")
```

effectively resolves:

```text
auth.login.form.after_fields
```

## How You Normally Use It In A Render

The usual pattern is:

1. build the normal page UI
2. resolve the hook at the insertion point
3. add the returned components to the builder
4. include their ids in the parent layout

Example:

```python
async def render(params: dict, session: dict):
    builder = module_sdk.ui.Builder()

    extra_widgets = await module_sdk.hooks.resolve_render_hook(
        "dashboard.after_stats",
        params=params,
        session=session,
    )

    for component in extra_widgets:
        builder.add(component)

    extra_ids = [component.id for component in extra_widgets]

    root = module_sdk.ui.Column(
        "dashboard_root",
        ["stats_row", "main_content", *extra_ids],
    )
    builder.add(root)
    return builder
```

That is the correct authoring style for slot owners.

## About `params`

`params` is the contextual payload passed to hook providers.

Use it for information the provider needs in order to decide what to render or how to configure the returned components.

Typical examples:

- current workspace id
- page state needed for extension behavior
- route or filter context

### Why `params` Exists

Without `params`, providers would have to guess too much from global state or session data.

Passing a small explicit params dict makes hook contracts easier to understand and less brittle.

## About `session`

If you omit `session`, the facade uses the current SDK session.

If you pass a truthy session explicitly, that session object is forwarded to provider callbacks.

One implementation detail matters here: the current facade uses `session or self.sdk.session` when forwarding the call. In practice that means an explicit empty dict behaves like “use the current SDK session” rather than “forward an empty session”.

In normal page renders, passing the current render session is usually the clearest choice anyway.

## Return Value

The method returns a list of normalized `Component` instances.

That list may be:

- empty when no providers match
- a list of one component
- a list of many components contributed by multiple providers

If no callbacks are registered and the slot is optional, the method simply returns an empty list.

That behavior is what makes hook resolution safe to integrate directly into normal layout code.

## Why This Is Better Than Hardcoded Cross-Module Imports

Without hooks, extending another module’s UI usually degenerates into:

- hardcoded imports
- explicit dependency chains
- special cases inside the owner module

`resolve_render_hook(...)` avoids that by keeping the slot owner agnostic about which modules are providing content.

The owner just asks for contributions to a named slot and renders whatever valid providers return.

