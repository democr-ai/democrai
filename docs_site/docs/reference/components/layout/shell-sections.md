# Layout Shell Sections

[<- Back to Layout Components](./index.md)

This page describes the module shell pattern: navigation and frame components live in one surface, while route content is rendered into a named `SurfaceHost`.

## Structure

A module navigation shell has two surfaces:

- Shell surface: sidebar, navigation tree, splitters, scroll wrappers, and `SurfaceHost`.
- Content surface: the route-specific UI rendered into the host.

The shell is responsible for layout. The content surface is responsible for page content.

## Shell Surface

Build the shell with concrete layout components. The common shape is:

- `Row` or `Splitter` as the root frame.
- `Sidebar` or `Column` for navigation.
- `ScrollArea` around the content region when the hosted content should scroll.
- `SurfaceHost` with a stable `surface_id` for the content surface.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Module shell surface example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="shell-surface-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="shell-surface-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="shell-surface-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder = sdk.ui.Builder()

builder.add(sdk.ui.TreeView("module_nav", nodes=nodes, click_action="nav"))

sidebar = sdk.ui.Sidebar("module_sidebar", ["module_nav"])
sidebar.set_property("width", 260)
sidebar.set_property("max_width", 360)
builder.add(sidebar)

host = sdk.ui.SurfaceHost("module_content_host", surface_id="module_content")
builder.add(host)

content_scroll = sdk.ui.ScrollArea("module_content_scroll", [host.id])
content_scroll.set_property("stretch", True)
content_scroll.set_property("transparent", True)
builder.add(content_scroll)

shell = sdk.ui.Row("module_shell", [sidebar.id, content_scroll.id])
shell.set_property("align", "fill")
shell.set_property("stretch", True)
builder.add(shell)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="shell-surface-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: module_shell
  align: fill
  stretch: true
  children:
    - kind: Sidebar
      id: module_sidebar
      width: 260
      max_width: 360
      children:
        - module_nav
    - kind: ScrollArea
      id: module_content_scroll
      stretch: true
      transparent: true
      children:
        - kind: SurfaceHost
          id: module_content_host
          surface_id: module_content</code></pre></div>
  </div>
</div>

## Content Surface

Every content route that should appear inside the shell must render to the same named surface used by `SurfaceHost`.

```python
async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    builder.set_surface("module_content", shell_route="/module/shell")

    builder.add(sdk.ui.Title("page_title", "Overview", level=2))
    builder.add(sdk.ui.Column("page_root", ["page_title"]))
    return builder
```

`shell_route` tells the runtime which shell route owns the host for this surface.

## SDK Helpers

Use `prepare_shell_surface(...)` in content routes when you want the SDK to set the target surface and create an empty content container:

```python
content_id = sdk.ui.prepare_shell_surface(
    builder,
    surface_id="module_content",
    shell_route="/module/shell",
    content_component_id="module_content_root",
)
```

Use `mount_shell_frame(...)` in the shell route when the module follows the common navigation/content pattern:

```python
root_id, host_id = sdk.ui.mount_shell_frame(
    builder,
    nav_component_id="module_nav",
    content_surface_id="module_content",
    root_id="module_root",
    splitter_id="module_splitter",
    nav_container_id="module_nav_container",
    content_scroll_id="module_content_scroll",
    content_host_id="module_content_host",
    splitter_sizes=[260, 860],
    splitter_max_sizes=[360, 0],
)
```

The helper builds:

- root `Row`
- `Splitter`
- navigation `Column`
- content `ScrollArea`
- `SurfaceHost`

## Navigation

Navigation components should change route, not replace the hosted content manually. For a tree or list navigation item, use `click_action="nav"` and route paths that render into the content surface.

```python
builder.add(
    sdk.ui.TreeView(
        "module_nav",
        nodes=[
            {"id": "overview", "label": "Overview", "path": "/module"},
            {"id": "settings", "label": "Settings", "path": "/module/settings"},
        ],
        click_action="nav",
        click_mode="single",
        selection_mode="single",
        active_as_selection=True,
    )
)
```

Use `sdk.ui.nav_active_path_rule(path)` for active navigation state when the navigation component supports it.

## Responsibilities

Shell surface:

- navigation layout
- sidebar or split sizing
- scroll container around the host
- `SurfaceHost(surface_id=...)`

Content surface:

- page-specific titles, forms, tables, charts, and actions
- data model for that surface
- updates targeting its own `surface_id`

## Notes

- Keep `surface_id` stable. Changing the content route should render a new content surface update, not mutate the host id.
- Do not put module content directly in the shell when it is route-specific.
- Do not use `SurfaceHost` as a generic container. It is a mount point for another surface.
- Put `ScrollArea` around the host when the hosted content must scroll inside the shell frame.
