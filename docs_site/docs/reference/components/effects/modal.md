# Modal

[<- Back to Effects](./index.md)

A modal is an auxiliary surface opened by the core `open_modal` action. The action resolves a normal page route, wraps the route roots in a dialog frame, renders the result into the `modal` surface, and starts rendering that surface on the client.

The page rendered in the modal is authored like any other route. In the test page, the trigger loads `/components/overlays/modal_sample`.

When `open_modal` resolves the target route, the current route parameters are passed as parent parameters to the loaded page. Use this to open detail/edit modal pages from parameterized routes without duplicating the route context in the button params. Explicit params on the loaded route still belong to the loaded route; avoid reusing the same names for unrelated meanings.

## Trigger

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Modal trigger example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="modal-trigger-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="modal-trigger-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="modal-trigger-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.Button(
    "open_modal_520",
    "Modal 520",
    action="open_modal",
    params={
        "path": "/components/overlays/modal_sample",
        "title": "Effects modal 520",
        "width": 520,
    },
    variant="primary",
    icon="ric.window-line",
)

sdk.ui.Button(
    "open_modal_720",
    "Modal 720",
    action="open_modal",
    params={
        "path": "/components/overlays/modal_sample",
        "title": "Effects modal 720",
        "width": 720,
    },
    variant="primary",
    icon="ric.window-line",
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="modal-trigger-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: open_modal_520
  label: Modal 520
  action: open_modal
  params: {path: /components/overlays/modal_sample, title: Effects modal 520, width: 520}
  variant: primary
  icon: ric.window-line
- kind: Button
  id: open_modal_720
  label: Modal 720
  action: open_modal
  params: {path: /components/overlays/modal_sample, title: Effects modal 720, width: 720}
  variant: primary
  icon: ric.window-line</code></pre></div>
  </div>
</div>

## Parameters

| Parameter | Type | Description |
|---|---|---|
| `path` | `str` | Route to load inside the modal. Required. |
| `title` | `str` | Dialog title used by the modal frame. |
| `width` | `int` | Modal width in pixels. Clients cap it to the available viewport/window width. |

## Closing

Close the modal with the core `close_modal` action:

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Modal closing example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="modal-close-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="modal-close-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="modal-close-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.Button(
    "close_modal",
    "Close modal",
    action="close_modal",
    variant="primary",
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="modal-close-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: close_modal
  label: Close modal
  action: close_modal
  variant: primary</code></pre></div>
  </div>
</div>

## Page Content

The modal body route returns regular components:

```python
async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    builder.add(sdk.ui.Title("modal_title", "Sample Page", 2))
    builder.add(sdk.ui.Text("modal_text", "Loaded from a dedicated route."))
    builder.add(
        sdk.ui.Button(
            "close_modal",
            "Close modal",
            action="close_modal",
            variant="primary",
        )
    )
    builder.add(sdk.ui.Column("modal_root", ["modal_title", "modal_text", "close_modal"]))
    return builder
```
