# Layout Composition Primitives

[<- Back to Layout Components](./index.md)

This page covers the components used to build most page trees:

- `Column`
- `Row`
- `Grid`

## Build Pattern

Use `Column` as the default page root. Add `Row` where you need horizontal grouping and `Grid` when the children must be arranged in a real grid. Use [FlexContainer](../complex/flexcontainer.md) only for fill or spacer behavior without directional semantics.

Rooted YAML example:

```yaml
- kind: Column
  id: settings_page
  spacing: 16
  children:
    - kind: Row
      id: settings_toolbar
      align: fill
      spacing: 8
      children:
        - kind: Title
          id: settings_title
          text: Settings
          level: 2
        - kind: FlexContainer
          id: settings_toolbar_spacer
        - kind: Button
          id: settings_save
          label: Save
    - kind: Grid
      id: settings_cards
      columns: 2
      children:
        - kind: Card
          id: settings_card_general
          children:
            - kind: Text
              id: settings_card_general_text
              text: General settings
        - kind: Card
          id: settings_card_notifications
          children:
            - kind: Text
              id: settings_card_notifications_text
              text: Notification settings
```

## Column

Use `Column` as the default structural container for full pages and vertical sections.

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `children` | yes | yes | yes | Standard container child list |
| `align` | yes | yes | yes | Typical values in previews: `fill`, `top`, `center`, `bottom` |
| `spacing` | yes | yes | yes | Common and useful in real layouts |
| `style` | yes | yes | yes | Standard styling |

Runtime pattern:

```python
return sdk.effects.respond(
    sdk.effects.ui_collection_append("settings_page", "children", new_section),
    sdk.effects.ui_property_update("settings_page", "align", "fill"),
)
```

## Row

Use `Row` for horizontal bars, inline control groups, action toolbars, and side-by-side sections.

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `children` | yes | yes | yes | Standard container child list |
| `align` | yes | yes | yes | Typical values in previews: `fill`, `left`, `center`, `right` |
| `spacing` | yes | yes | yes | Common and useful in real layouts |
| `style` | yes | yes | yes | Standard styling |

Runtime pattern:

```python
return sdk.effects.respond(
    sdk.effects.ui_collection_remove("settings_toolbar", "children", {"id": "settings_save"}),
    sdk.effects.ui_property_update("settings_toolbar", "align", "center"),
)
```

## Grid

Use `Grid` when the section is a real multi-cell grid layout and the children should be placed into evenly repeated columns.

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `children` | yes | yes | yes | Grid items rendered cell by cell |
| `columns` | yes | yes | yes | Number of repeated grid columns |
| `style` | yes | yes | yes | Standard styling |

Runtime pattern:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update("settings_cards", "columns", 3),
    sdk.effects.ui_collection_append("settings_cards", "children", extra_card),
)
```

## Practical Guidance

- Start with `Column`.
- Use `Row` for local horizontal groups, not as a full page root by default.
- Use [FlexContainer](../complex/flexcontainer.md) only when `Column` or `Row` would add false semantics.
- Use `Grid` when the visual model is explicitly a grid, not just a vertical section with columns in the abstract.
