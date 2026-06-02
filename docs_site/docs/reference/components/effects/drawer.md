# Drawer

[<- Back to Effects](./index.md)

A drawer is an auxiliary surface opened by the core `open_drawer` action. The action resolves a normal page route and renders its roots into the `drawer` surface.

The page rendered in the drawer is authored like any other route. In the test page, the triggers load `/components/overlays/drawer_sample`.

When `open_drawer` resolves the target route, the current route parameters are passed as parent parameters to the loaded page. Use this to open contextual drawers from parameterized routes without copying the same context into every trigger. Explicit params on the loaded route still belong to the loaded route; avoid reusing the same names for unrelated meanings.

## Trigger

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Drawer trigger example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="drawer-trigger-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="drawer-trigger-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="drawer-trigger-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.Button(
    "open_drawer_right",
    "Drawer right",
    action="open_drawer",
    params={
        "path": "/components/overlays/drawer_sample",
        "position": "right",
        "dim": 520,
    },
    variant="default",
    icon="ric.sidebar-unfold-line",
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="drawer-trigger-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: open_drawer_right
  label: Drawer right
  action: open_drawer
  params:
    path: /components/overlays/drawer_sample
    position: right
    dim: 520
  variant: default
  icon: ric.sidebar-unfold-line</code></pre></div>
  </div>
</div>

## Parameters

| Parameter | Type | Description |
|---|---|---|
| `path` | `str` | Route to load inside the drawer. Required. |
| `position` | `str` | Drawer edge: `right`, `left`, `top`, or `bottom`. Defaults to `right`. |
| `dim` | `int` | Drawer dimension in pixels. For `left`/`right` it controls width; for `top`/`bottom` it controls height. |

## Positions

The test page includes all supported positions:

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Drawer positions example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="drawer-positions-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="drawer-positions-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="drawer-positions-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.Button(
    "open_drawer_right_360",
    "Drawer right 360",
    action="open_drawer",
    params={
        "path": "/components/overlays/drawer_sample",
        "position": "right",
        "dim": 360,
    },
    variant="default",
    icon="ric.sidebar-unfold-line",
)

sdk.ui.Button(
    "open_drawer_right_640",
    "Drawer right 640",
    action="open_drawer",
    params={
        "path": "/components/overlays/drawer_sample",
        "position": "right",
        "dim": 640,
    },
    variant="default",
    icon="ric.sidebar-unfold-line",
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="drawer-positions-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: open_drawer_right_360
  label: Drawer right 360
  action: open_drawer
  params: {path: /components/overlays/drawer_sample, position: right, dim: 360}
  variant: default
  icon: ric.sidebar-unfold-line
- kind: Button
  id: open_drawer_right_640
  label: Drawer right 640
  action: open_drawer
  params: {path: /components/overlays/drawer_sample, position: right, dim: 640}
  variant: default
  icon: ric.sidebar-unfold-line
- kind: Button
  id: open_drawer_left_420
  label: Drawer left 420
  action: open_drawer
  params: {path: /components/overlays/drawer_sample, position: left, dim: 420}
  variant: default
  icon: ric.sidebar-unfold-line
- kind: Button
  id: open_drawer_top_240
  label: Drawer top 240
  action: open_drawer
  params: {path: /components/overlays/drawer_sample, position: top, dim: 240}
  variant: default
  icon: ric.sidebar-unfold-line</code></pre></div>
  </div>
</div>

## Closing

Close the drawer with the core `close_drawer` action:

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Drawer closing example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="drawer-close-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="drawer-close-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="drawer-close-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.Button(
    "close_drawer",
    "Close drawer",
    action="close_drawer",
    variant="default",
    icon="ric.close-line",
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="drawer-close-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: close_drawer
  label: Close drawer
  action: close_drawer
  variant: default
  icon: ric.close-line</code></pre></div>
  </div>
</div>

## Page Content

The drawer body route returns regular components:

```python
async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    builder.add(sdk.ui.Title("drawer_title", "Sample Page", 3))
    builder.add(sdk.ui.Text("drawer_text", "Loaded from a dedicated route."))
    builder.add(sdk.ui.Badge("drawer_badge", "Drawer Surface", variant="success"))
    builder.add(sdk.ui.Column("drawer_root", ["drawer_title", "drawer_text", "drawer_badge"]))
    return builder
```
