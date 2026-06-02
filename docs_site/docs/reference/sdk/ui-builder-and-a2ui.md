# UI Builder and A2UI

`sdk.ui.Builder` and `sdk.ui`

## Purpose

This document describes the low-level builder and protocol helpers exposed through the `ui` domain.

In Democr.ai, this layer is the project implementation of the A2UI approach described at [a2ui.org](https://a2ui.org/): the server builds declarative UI structures and update messages, and the client renders them with its own components instead of executing arbitrary UI code.

That is why this page is about surface structure, data-model values, and incremental update payloads. `sdk.ui.Builder` is the programmatic entrypoint used to construct those A2UI-style messages inside the SDK.

The important architectural point is that this is not a separate public root-level API. The builder lives under `sdk.ui`.

At module level, the main public entrypoints are:

- `sdk.ui.Builder`
- `sdk.ui.<Component>`
- bound helpers re-exported from `sdk.ui`

Use this layer when you need to:

- build a surface programmatically
- set data model values
- choose a template
- generate surface update messages
- generate property/collection update payloads

If you are authoring normal module UI, prefer starting from [the `ui` domain overview](./ui/index.md). Use this document set when you need the lower-level builder and payload API specifically.

## Overview

### Where These APIs Are Used

These low-level UI methods are not limited to one phase of the module lifecycle.

The first common use is inside a render flow. In that case, `sdk.ui.Builder` is used to assemble the surface, seed its data model, choose the template, and serialize the initial `surfaceUpdate` payload that the client mounts.

The second common use is inside actions and asynchronous runtime flows. Once the interface already exists on the client, the same message shapes become useful as targeted updates: property changes, collection patches, data-model updates, or explicit surface removal. In normal synchronous actions, these updates usually come back as returned effects. In long-running or detached flows, they are published to connected clients through the `publish_*` helpers in `sdk.effects`.

So the mental model is:

- render code builds the initial surface state through the builder
- actions either return incremental UI effects or publish the same kinds of updates when the response is no longer tied to the original request

Example render-side usage:

```python
builder = sdk.ui.Builder()
builder.set_template("full", session=session)
builder.set_surface("users_main")
builder.set_data("/filters/search", "")
builder.set_store("/drafts/search", "", scope="page")
builder.add(sdk.ui.Text("title", "Users"))

return builder.build_surface_update_payload("users_main")
```

Example action-side returned update:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update(
        "status_badge",
        "text",
        {"literalString": "Saved"},
        surface_id="users_main",
    )
)
```

Example action-side published update:

```python
await sdk.effects.publish_property_update(
    stream_id,
    "status_badge",
    "text",
    {"literalString": "Saved"},
    surface_id="users_main",
)
```

## Sections

- [Builder and Stores](./ui-builder-and-a2ui-builder-and-stores.md)
- [Builder Methods](./ui-builder-and-a2ui-builder-methods.md)
- [Bindings and Conditions](./ui-builder-and-a2ui-bindings-and-conditions.md)
- [Samples and Notes](./ui-builder-and-a2ui-samples-and-notes.md)
