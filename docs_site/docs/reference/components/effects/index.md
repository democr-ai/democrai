# Effects

[<- Back to Components Index](../index.md)

Effects are runtime responses returned by actions. They are not standalone visual components: a component, usually a `Button`, triggers an action, and the action returns one or more effects for the client to execute.

Use effects for transient UI behavior such as notifications, modal surfaces, drawer surfaces, navigation, copy-to-clipboard, or incremental UI updates. Toasts are returned by module actions through `sdk.effects`; modal and drawer route loading is handled by core actions.

## Pages

- [Toast](./toast.md)
- [Modal](./modal.md)
- [Drawer](./drawer.md)
- [DropdownMenu](./dropdownmenu.md)
- [BackgroundTask](./backgroundtask.md)
- [StreamBinding](./streambinding.md)

## Trigger Pattern

The component only declares the action to run:

```python
sdk.ui.Button(
    "show_toast",
    "Show toast",
    action="components.test_effect_toast",
    params={"variant": "success"},
)
```

The action returns the effect:

```python
@action("test_effect_toast")
async def test_effect_toast(ctx: dict, session: dict, sdk) -> dict:
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Success toast",
                "text": "Saved successfully.",
                "variant": "success",
            },
        )
    )
```

For modal and drawer surfaces, call the core actions directly from the trigger:

```python
sdk.ui.Button(
    "open_modal",
    "Open modal page",
    action="open_modal",
    params={"path": "/components/overlays/modal_sample", "width": 720},
)

sdk.ui.Button(
    "open_drawer",
    "Open drawer",
    action="open_drawer",
    params={
        "path": "/components/overlays/drawer_sample",
        "position": "right",
        "dim": 520,
    },
)
```

The core resolves the route, builds the target surface, and renders it into `modal` or `drawer`.
