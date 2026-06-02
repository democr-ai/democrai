# Layout Components

[<- Back to Components Index](../index.md)

Layout components define the component tree: vertical and horizontal grouping, page-shell regions, scrollable content, split panes, and hosted surfaces.

Use this section when the question is where a component should live, how it should size, and which part of the page should scroll.

## Recommended Path

1. Start with [Composition Primitives](./composition-primitives.md) for `Column`, `Row`, and `Grid`.
2. Use [Shell Sections](./shell-sections.md) when a module needs navigation plus hosted route content.
3. Use [Ready Layouts](./ready-layouts/index.md) when the page matches a common full-page structure.
4. Read the individual component page when you need binding, direct updates, visibility, or permissions for that component.

## Component Groups

Core composition:

- [Column](./column.md)
- [Row](./row.md)
- [Grid](../complex/grid.md)
- [Container](./container.md)

Page-shell sections:

- [Header](./header.md)
- [Sidebar](./sidebar.md)
- [ContentArea](./contentarea.md)
- [SurfaceHost](./surfacehost.md)

Scrollable and resizable regions:

- [ScrollArea](./scrollarea.md)
- [Splitter](./splitter.md)

Ready page structures:

- [Sidebar + Content](./ready-layouts/sidebar-content.md)
- [Header + Content](./ready-layouts/header-content.md)
- [Header + Sidebar + Content](./ready-layouts/header-sidebar-content.md)
- [Sidebar + Content Header](./ready-layouts/sidebar-content-header.md)
- [Sidebar + Splitted Content](./ready-layouts/sidebar-splitted-content.md)

## Layout Rules

- Use `Column` for vertical order.
- Use `Row` for horizontal order.
- Use `Grid` only when the visual model is a real grid.
- Use `Header`, `Sidebar`, and `ContentArea` for semantic shell regions.
- Put `ScrollArea` around content that must scroll inside a fixed-height shell.
- Put `SurfaceHost` where a module shell should mount route content from another surface.
- Use [FlexContainer](../complex/flexcontainer.md) only for fill or spacer behavior without directional semantics.

## Module Shells

For module navigation shells, keep shell and content responsibilities separate:

- The shell route builds navigation, frame layout, scroll wrappers, and `SurfaceHost`.
- Content routes render into the `SurfaceHost.surface_id` with `builder.set_surface(...)` or `prepare_shell_surface(...)`.

See [Shell Sections](./shell-sections.md) and [SurfaceHost](./surfacehost.md) for the full pattern.

## Notes

- `Container` is a base SDK class, not a standalone renderable component.
- `Card`, `DashboardWidget`, `Grid`, and `Tabs` are documented under Complex.
- Modal and drawer usage belongs to Effects, not Layout.
