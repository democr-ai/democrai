# Provider Callbacks And Runtime Behavior

This section explains what happens after a slot owner calls `resolve_render_hook(...)`.

That includes:

- how providers are registered
- what provider callbacks can receive
- what they are allowed to return
- how the runtime normalizes component ids
- what warnings and errors look like

## Provider Registration

Providers are registered through `@render_hook(...)`, not through the `Hooks` facade.

Safe example:

```python
@render_hook("auth.login.form.after_fields", priority=100)
def provide_login_extension(params=None, session=None, module_sdk=None):
    return module_sdk.ui.Text("login_hint", "Extra content")
```

The base helper expects a fully qualified hook key. If the key is not fully qualified, registration is skipped with a warning.

Scoped decorator binding can qualify names for you in some module authoring paths, but for public SDK usage the safe rule is:

- slot owners may work with relative names inside `resolve_render_hook(...)`
- providers should register against the fully qualified hook key

## What Provider Callbacks Can Receive

The runtime inspects the provider callback signature and injects parameters by name.

Supported names are:

- `params`
- `session`
- `sdk`, `module_sdk`, or `democrai.sdk`
- `hook_name`

Unlike module events, arbitrary keys from `params` are not injected one by one into the callback signature.

That means this is the expected style:

```python
@render_hook("auth.login.form.after_fields")
def provide_widget(params=None, session=None, module_sdk=None, hook_name=None):
    ...
```

If your provider needs contextual values, read them from the `params` dict.

## What Provider Callbacks Can Return

This is one of the most important details of the runtime contract.

A render-hook callback may return:

- one `Component`
- `list[Component]`
- a `Builder`
- `None`

Anything else is a runtime type error.

### Returning One Component

This is the simplest and most common case.

```python
@render_hook("crm.dashboard.after_stats")
def provide_card(module_sdk=None, params=None):
    card = module_sdk.ui.Card("crm_extension_card", ["crm_extension_text"])
    return card
```

### Returning Multiple Components

If your provider naturally contributes more than one sibling component, you can return a list of components.

```python
@render_hook("crm.dashboard.after_stats")
def provide_widgets(module_sdk=None):
    return [
        module_sdk.ui.Text("widget_a", "A"),
        module_sdk.ui.Text("widget_b", "B"),
    ]
```

### Returning A Builder

You can also return a `Builder`. In that case, the runtime extracts its root components and normalizes them into the final result list.

This is useful when the provider needs a small self-contained mini-layout with multiple internal components.

### Returning `None`

Returning `None` means "do not contribute anything right now".

That is a valid opt-out path.

## Component ID Prefixing

The runtime deep-copies contributed components and prefixes component ids with the provider module name.

This behavior is extremely important.

If a provider from module `analytics` returns a component with id `login_hint`, the resolved id becomes something like:

```text
analytics_login_hint
```

The runtime also rewrites child references accordingly.

### Why This Happens

Without id prefixing, two different modules could easily return components with the same ids and collide inside the owner page.

The prefixing step is what makes multi-module hook composition safe.

## Execution Order

Providers are executed in registry order sorted by:

- higher `priority` first
- then newer registration order for ties

That means a larger priority value runs earlier, not later.

This is an easy detail to get wrong if you assume lower numbers run first as in some other systems.

If order matters, set explicit priorities and document why.

## What Happens When No Providers Exist

If no providers are registered for the resolved hook:

- the runtime returns an empty list
- it warns when the slot was undeclared
- it warns when the slot was declared but marked non-optional
- it stays quiet when the slot is declared and `optional=True`

This is why the `optional` flag on `@render_hook_slot(...)` matters.

Use `optional=True` when the page should render normally even if nobody extends the slot.

Use `optional=False` when you want missing providers to surface as a warning because the architecture expects that slot to be implemented.

## What Happens When A Provider Raises

If a provider callback throws an exception:

- the runtime logs an error
- that provider contributes nothing
- resolution continues with the remaining providers

This isolation is intentional. One broken provider should not usually stop the owner module from rendering its page.

But you should still treat provider errors as real bugs, because they silently remove contributed UI from the final result.

## What Happens When A Provider Returns The Wrong Type

This is different from a callback exception.

If the callback returns an invalid type, the normalization layer raises a `TypeError`. That error is not swallowed by the same isolation path used for callback exceptions, so it can fail the whole hook resolution call.

In practice, this means wrong return types are more severe than ordinary callback errors.

Examples of invalid returns:

- plain strings
- dicts
- lists containing non-`Component` items

So the safe rule is simple:

- return `Component`, `list[Component]`, `Builder`, or `None`
- do not rely on the runtime to quietly ignore malformed return values

## Practical Design Guidance

When designing a new render-hook extension point:

1. declare the slot
2. choose a stable, fully qualified name that describes the UI position
3. keep `params` small and explicit
4. make the slot optional unless the architecture really depends on a provider
5. assume provider ids will be prefixed and avoid relying on raw unprefixed ids across module boundaries

If you follow those rules, render hooks stay predictable instead of turning into invisible UI coupling.

