# SurfaceHost

[<- Back to Layout Components](./index.md)

## Definition

`SurfaceHost` reserves a region of the current layout for another named UI surface.

## Scope

Use `SurfaceHost` when a module shell and its content are rendered as separate surfaces. The shell surface owns navigation, framing, and the host region. The content surface is rendered into the host by matching the host `surface_id`.

Do not use `SurfaceHost` as a generic visual container. Use `Column`, `Row`, `ContentArea`, `ScrollArea`, or `FlexContainer` when the children belong to the same surface.

`id` and `surface_id` identify different things. `id` is the component id of the host inside the shell surface. `surface_id` is the name of the separate content surface that should mount inside that host.

```python
host = sdk.ui.SurfaceHost("module_content_host", surface_id="module_content")
builder.add(host)
```

The content route must use the same surface name:

```python
builder.set_surface("module_content", shell_route="/module/shell")
```

The required match is `SurfaceHost.surface_id == builder.surface_id`. The host component id does not need to match the surface id.

Do not rely on `SurfaceHost.children` for fallback labels or placeholder content. The web client renders `SurfaceHost` as a mount point and displays the hosted surface when it exists; local placeholder content should live outside the host.

## Properties

| Property | Type | Default | Notes |
|---|---|---|---|
| `surface_id` | `string` | required | Named surface mounted by this host. Treat it as static for the host. |
| `children` | `list[str | Component]` | `[]` | Inherited container field. Do not use it for cross-client placeholder content. |
| `style` | `string` | client default | Standard style property. |

## Static Host

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="SurfaceHost static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>host = sdk.ui.SurfaceHost(
    "module_content_host",
    surface_id="module_content",
)
builder.add(host)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: SurfaceHost
  id: module_content_host
  surface_id: module_content</code></pre></div>
  </div>
</div>

## Module Shell

A navigation shell normally places `SurfaceHost` beside module navigation. Wrap the host in the layout containers that define scrolling, splitting, or sizing.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="SurfaceHost module shell example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-shell-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-shell-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-shell-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>nav = sdk.ui.Column("module_nav", ["nav_overview", "nav_settings"])
builder.add(nav)

sidebar = sdk.ui.Sidebar("module_sidebar", [nav.id])
sidebar.set_property("width", 220)
sidebar.set_property("max_width", 220)
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
  <div class="docs-code-group__panel" id="surfacehost-shell-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: module_shell
  align: fill
  stretch: true
  children:
    - kind: Sidebar
      id: module_sidebar
      width: 220
      max_width: 220
      children:
        - kind: Column
          id: module_nav
          children:
            - nav_overview
            - nav_settings
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

The content route must render into the same `surface_id` used by the host.

```python
async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    builder.set_surface("module_content", shell_route="/module/shell")

    builder.add(sdk.ui.Title("content_title", "Overview", level=2))
    builder.add(sdk.ui.Column("content_root", ["content_title"]))
    return builder
```

The SDK helper `prepare_shell_surface(...)` creates the same surface setup and adds an empty content container:

```python
content_id = sdk.ui.prepare_shell_surface(
    builder,
    surface_id="module_content",
    shell_route="/module/shell",
    content_component_id="module_content_root",
)
```

## Store Binding

Bind `style` when the host frame is driven by page or global store state.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="SurfaceHost store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.set_store("/components_test/surfacehost/style", "", scope="page")

host = sdk.ui.SurfaceHost("module_content_host", surface_id="module_content")
host.set_property(
    "style",
    bound.store("/components_test/surfacehost/style", scope="page", default=""),
)
builder.add(host)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: SurfaceHost
  id: module_content_host
  surface_id: module_content
  style: {type: store, scope: page, path: /components_test/surfacehost/style, default: ""}</code></pre></div>
  </div>
</div>

## Data Model Binding

Use data-model binding when the host style comes from the current surface data.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="SurfaceHost data binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.set_data("/components_test/surfacehost_model/style", "")

host = sdk.ui.SurfaceHost("module_content_host", surface_id="module_content")
host.set_property(
    "style",
    bound.data("/components_test/surfacehost_model/style", default=""),
)
builder.add(host)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: SurfaceHost
  id: module_content_host
  surface_id: module_content
  style: "@data/components_test/surfacehost_model/style"</code></pre></div>
  </div>
</div>

## Property Updates

Declare capabilities before updating `style` directly. Do not update `surface_id` at runtime; create a host with the target surface id.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="SurfaceHost property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>host = sdk.ui.SurfaceHost("module_content_host", surface_id="module_content")
host.allow("style.set")
builder.add(host)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: SurfaceHost
  id: module_content_host
  surface_id: module_content
  capabilities: [style.set]</code></pre></div>
  </div>
</div>

## Visibility And Permissions

`show_if`, `hide_if`, and `required_permissions` are available on `SurfaceHost`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="SurfaceHost visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="surfacehost-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>host.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/surfacehost_show", scope="page", default=True), "op": "==", "right": True}
    ]
})

host.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/surfacehost_hide", scope="page", default=False), "op": "==", "right": True}
    ]
})

host.set_required_permissions(["components.layout.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="surfacehost-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: SurfaceHost
  id: surfacehost_show_if
  surface_id: module_content
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/surfacehost_show, default: true}
        op: "=="
        right: true

- kind: SurfaceHost
  id: surfacehost_hide_if
  surface_id: module_content
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/surfacehost_hide, default: false}
        op: "=="
        right: true

- kind: SurfaceHost
  id: surfacehost_required_permissions
  surface_id: module_content
  required_permissions: [components.layout.view]</code></pre></div>
  </div>
</div>

## Notes

- The host `surface_id` must match the content builder surface id.
- Use one active host for a given content `surface_id` in a shell.
- Keep navigation and content surface concerns separate.
- Put scrolling or split behavior around `SurfaceHost`, not inside the content surface by default.
- Use `builder.set_surface(...)` or `prepare_shell_surface(...)` for routes that render into the host.
