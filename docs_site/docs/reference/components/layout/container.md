# Container

[<- Back to Layout Components](./index.md)

## Definition

`Container` is the SDK base class for UI components that own a `children` collection.

## Scope

Do not use `Container` as a standalone module UI component. It has no dedicated desktop or web renderer, so declarations such as `kind: Container` are not valid examples for renderable UI.

Use concrete renderable containers instead:

- `Column` for vertical layout.
- `Row` for horizontal layout.
- `Header`, `Sidebar`, and `ContentArea` for page-shell regions.
- `ScrollArea`, `Splitter`, `Grid`, `Flow`, and `FlexContainer` for specialized layout behavior.

## SDK Contract

`Container` extends `Component` and adds constructor support for `children`.

```python
Container(
    id: str,
    children: Optional[List[Union[str, Component]]] = None,
)
```

It also exposes `set_children(...)` for subclasses:

```python
def set_children(self, children: List[Union[str, Component]]):
    self.children = children
    return self
```

## Inherited Behavior

Concrete subclasses inherit the shared `children` serialization behavior from `Component` and `Container`.

When a child is a component object, it is serialized inline. When a child is a string, it is kept as a component id reference.

```python
column = sdk.ui.Column(
    "content_stack",
    [
        sdk.ui.Text("inline_item", "Inline child"),
        "referenced_item",
    ],
)
```

This serializes to the protocol `children.explicitList` with one inline component definition and one id reference.

## Runtime Updates

Runtime child updates are implemented by concrete renderers, not by `Container` itself.

For example, `Column`, `Row`, `ScrollArea`, and other renderable containers can support collection patches on `children` when their renderer implements that behavior and the component declares the capability:

```python
column = sdk.ui.Column("content_stack", ["item_1"])
column.allow("children.append", "children.remove")
builder.add(column)
```

```python
return sdk.effects.respond(
    sdk.effects.ui_collection_append(
        "content_stack",
        "children",
        sdk.ui.Text("item_2", "Item 2").to_dict(),
        surface_id=ctx["_surface_id"],
    )
)
```

## Visibility And Permissions

`show_if`, `hide_if`, `required_permissions`, and capabilities are inherited from `Component`.

Apply them to concrete renderable components, not to `Container` directly:

```python
column = sdk.ui.Column("content_stack", ["item_1"])
column.set_show_if({
    "conditions": [
        {"left": bound.store("/can_view", scope="page", default=True), "op": "==", "right": True}
    ]
})
column.set_required_permissions(["components.layout.view"])
builder.add(column)
```

## Notes

- `Container` is a base class, not a layout primitive to place in a page tree.
- Do not publish `kind: Container` YAML examples for module UI.
- Document and test runtime behavior on the concrete component whose renderer implements it.
