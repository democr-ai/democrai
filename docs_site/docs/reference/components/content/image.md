# Image

[<- Back to Content Components](./index.md)

`Image` renders an image from a module asset path, runtime media URL, remote URL, or data URL. Use it when a module interface must display visual media with explicit dimensions and alternate text.

## Python Contract

```python
sdk.ui.Image(
    id: str,
    alt: Any,
    url: Any = "",
    width: int = 45,
    height: int = 45,
    lazy: bool = False,
)
```

`alt` and `url` accept literal values or bindings. `width` and `height` can also be bound in the rendered component and updated at runtime.

## Supported Properties

| Property | Type | Required | Python | YAML | Notes |
|---|---|---|---|---|---|
| `id` | `str` | yes | yes | yes | Stable component id |
| `alt` | `str | binding` | yes | constructor / `alt.set` | yes | Alternate text and accessibility label |
| `url` | `str | binding` | no | constructor / `url.set` | yes | Module asset path, media URL, remote URL, or data URL |
| `width` | `int | binding` | no | constructor / `width.set` | yes | Default `45` |
| `height` | `int | binding` | no | constructor / `height.set` | yes | Default `45` |
| `lazy` | `bool` | no | constructor / `lazy.set` | yes | Desktop defers loading until visible |
| `fit` | `str` | no | `set_property("fit", ...)` | yes | Renderer-level property; `container` expands to available width |
| `show_if` | rule | no | yes | yes | Generic visibility rule |
| `hide_if` | rule | no | yes | yes | Generic visibility rule |
| `required_permissions` | `list[str]` | no | yes | yes | Generic permission gate |

## Static Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Image static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="image-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Image(
        "components_test_image_static",
        "Mountain lake",
        url="assets/demo-image.png",
        width=280,
        height=180,
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="image-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Image
  id: components_test_image_yaml_static
  alt: "Mountain lake"
  url: "assets/demo-image.png"
  width: 280
  height: 180</code></pre></div>
  </div>
</div>

## Store Binding

Use page or global store bindings when the image follows client state. In Python use `bound.store(...)`; in YAML declare the binding object explicitly.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Image store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="image-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.Image(
        "components_test_image_store",
        bound.store("/components_test/image/alt", scope="page", default="Mountain lake"),
        url=bound.store("/components_test/image/url", scope="page", default="assets/demo-image.png"),
        width=bound.store("/components_test/image/width", scope="page", default=280),
        height=bound.store("/components_test/image/height", scope="page", default=180),
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="image-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Image
  id: components_test_image_yaml_store
  alt: {type: store, scope: page, path: /components_test/image/alt, default: "Mountain lake"}
  url: {type: store, scope: page, path: /components_test/image/url, default: "assets/demo-image.png"}
  width: {type: store, scope: page, path: /components_test/image/width, default: 280}
  height: {type: store, scope: page, path: /components_test/image/height, default: 180}</code></pre></div>
  </div>
</div>

## Data Model Binding

Use data model bindings when the value comes from the surface data model. These bindings are resolved from the constructor and update the component when the data model changes.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Image data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="image-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.Image(
        "components_test_image_data",
        bound.data("/components_test/image_model/alt", default="Mountain lake"),
        url=bound.data("/components_test/image_model/url", default="assets/demo-image.png"),
        width=bound.data("/components_test/image_model/width", default=280),
        height=bound.data("/components_test/image_model/height", default=180),
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="image-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Image
  id: components_test_image_yaml_data
  alt: "@data/components_test/image_model/alt"
  url: "@data/components_test/image_model/url"
  width: "@data/components_test/image_model/width"
  height: "@data/components_test/image_model/height"</code></pre></div>
  </div>
</div>

## Direct Property Update

Declare the update capabilities on the component before an action sends `propertyUpdate` messages.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Image property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="image-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Image(
        "components_test_image_live",
        "Mountain lake",
        url="assets/demo-image.png",
        width=280,
        height=180,
    ).allow("url.set", "alt.set", "width.set", "height.set")
)

builder.add(
    sdk.ui.Button(
        "components_test_image_set_alt_btn",
        "Set alternate",
        action="components.media_test_set",
        params={"component": "image", "state_key": "alternate"},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="image-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Image
  id: components_test_image_yaml_live
  alt: "Mountain lake"
  url: "assets/demo-image.png"
  width: 280
  height: 180
  capabilities: [url.set, alt.set, width.set, height.set]
- kind: Button
  id: components_test_image_yaml_set_alt_btn
  label: "Set alternate"
  variant: default
  action: components.media_test_set
  params: {component: image, state_key: alternate}</code></pre></div>
  </div>
</div>

The action updates store values, data model values, and direct component properties on the current surface:

```python
surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
sdk.effects.ui_property_update(
    "components_test_image_live",
    "url",
    "assets/demo_img.png",
    surface_id=surface_id,
)
```

## Visibility Rules

`show_if` and `hide_if` can observe real bindings. `required_permissions` declares the permission gate evaluated by the UI runtime.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Image visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="image-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>show_if = sdk.ui.Image(
    "components_test_image_show_if",
    "show_if visible",
    url="assets/demo_img.png",
    width=220,
    height=140,
)
show_if.set_show_if({
    "conditions": [{
        "left": bound.store("/components_test/visibility/image_show", scope="page", default=True),
        "op": "==",
        "right": True,
    }]
})
builder.add(show_if)

hide_if = sdk.ui.Image(
    "components_test_image_hide_if",
    "hide_if visible",
    url="assets/demo_img.png",
    width=220,
    height=140,
)
hide_if.set_hide_if({
    "conditions": [{
        "left": bound.store("/components_test/visibility/image_hide", scope="page", default=False),
        "op": "==",
        "right": True,
    }]
})
builder.add(hide_if)

gated = sdk.ui.Image(
    "components_test_image_required_permissions",
    "required_permissions gate",
    url="assets/demo_img.png",
    width=220,
    height=140,
)
gated.set_required_permissions(["components.media.visibility"])
builder.add(gated)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="image-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Image
  id: components_test_image_yaml_show_if
  alt: "show_if visible"
  url: "assets/demo_img.png"
  width: 220
  height: 140
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/image_show, default: true}
        op: "=="
        right: true
- kind: Image
  id: components_test_image_yaml_hide_if
  alt: "hide_if visible"
  url: "assets/demo_img.png"
  width: 220
  height: 140
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/image_hide, default: false}
        op: "=="
        right: true
- kind: Image
  id: components_test_image_yaml_required_permissions
  alt: "required_permissions gate"
  url: "assets/demo_img.png"
  width: 220
  height: 140
  required_permissions: [components.media.visibility]</code></pre></div>
  </div>
</div>

The test page updates the observed store flags with the same action used by Python and YAML declarations:

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Image visibility controls example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-visibility-controls-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="image-visibility-controls-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="image-visibility-controls-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Button(
        "components_test_image_show_off_btn",
        "Hide show_if",
        action="components.media_test_visibility_set",
        params={"component": "image", "flag": "show", "value": False},
        variant="default",
    )
)
builder.add(
    sdk.ui.Button(
        "components_test_image_hide_on_btn",
        "Hide hide_if",
        action="components.media_test_visibility_set",
        params={"component": "image", "flag": "hide", "value": True},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="image-visibility-controls-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: components_test_image_yaml_show_off_btn
  label: "Hide show_if"
  variant: default
  action: components.media_test_visibility_set
  params: {component: image, flag: show, value: false}
- kind: Button
  id: components_test_image_yaml_hide_on_btn
  label: "Hide hide_if"
  variant: default
  action: components.media_test_visibility_set
  params: {component: image, flag: hide, value: true}</code></pre></div>
  </div>
</div>

## Path Resolution and Asset Visibility

`Image.url` accepts several source forms, but module asset paths are the normal case for packaged module media.

- `assets/...` resolves to an asset inside the active module.
- `assets/protected/...` resolves to an asset inside the active module and requires an authenticated user.
- `/media/...` is already a client-facing media path and is used as-is by the clients.
- `http://...` and `https://...` are treated as remote URLs. On web they pass through the media proxy when the target is outside the core origin.
- `data:image/...` is treated as an inline data URL.

## Usage Guidance

- Use `alt` for descriptive alternate text.
- Use module asset paths such as `assets/demo-image.png` and `assets/demo_img.png` for packaged module media.
- Use store bindings when image state belongs to page or global client state.
- Use data model bindings when the image follows the surface data model.
- Use direct property updates for source or dimension changes without rebuilding the page.
