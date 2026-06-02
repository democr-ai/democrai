# QRCode

[<- Back to Content Components](./index.md)

`QRCode` renders a QR code from a textual payload. Use it for URLs, Wi-Fi configuration strings, identifiers, and other short values that must be scanned from the interface.

## Python Contract

```python
sdk.ui.QRCode(
    id: str,
    content: Any,
    *,
    size: int = 220,
    border: int = 4,
    fill_color: str = "#111111",
    back_color: str = "#ffffff",
)
```

`content` accepts literal values or bindings from the constructor. `size` is a numeric constructor value and can be updated directly at runtime when `size.set` is allowed.

## Supported Properties

| Property | Type | Required | Python | YAML | Notes |
|---|---|---|---|---|---|
| `id` | `str` | yes | yes | yes | Stable component id |
| `content` | `str | binding` | yes | constructor / `content.set` | yes | Text encoded into the QR code |
| `size` | `int` | no | constructor / `size.set` | yes | Rendered QR size |
| `border` | `int` | no | constructor / `border.set` | yes | Border size |
| `fill_color` | `str` | no | constructor / `fill_color.set` | yes | Foreground color |
| `back_color` | `str` | no | constructor / `back_color.set` | yes | Background color |
| `show_if` | rule | no | yes | yes | Generic visibility rule |
| `hide_if` | rule | no | yes | yes | Generic visibility rule |
| `required_permissions` | `list[str]` | no | yes | yes | Generic permission gate |

## Static Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="QRCode static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="qrcode-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.QRCode(
        "components_test_qrcode_static",
        "assets/demo-image.png",
        size=160,
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="qrcode-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: QRCode
  id: components_test_qrcode_yaml_static
  content: "assets/demo-image.png"
  size: 160</code></pre></div>
  </div>
</div>

## Store Binding

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="QRCode store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="qrcode-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.QRCode(
        "components_test_qrcode_store",
        bound.store("/components_test/qrcode/content", scope="page", default="assets/demo-image.png"),
        size=160,
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="qrcode-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: QRCode
  id: components_test_qrcode_yaml_store
  content: {type: store, scope: page, path: /components_test/qrcode/content, default: "assets/demo-image.png"}
  size: 160</code></pre></div>
  </div>
</div>

## Data Model Binding

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="QRCode data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="qrcode-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.QRCode(
        "components_test_qrcode_data",
        bound.data("/components_test/qrcode_model/content", default="assets/demo-image.png"),
        size=160,
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="qrcode-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: QRCode
  id: components_test_qrcode_yaml_data
  content: "@data/components_test/qrcode_model/content"
  size: 160</code></pre></div>
  </div>
</div>

## Direct Property Update

Declare `content.set` and `size.set` before an action sends direct updates to the rendered QR code.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="QRCode property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="qrcode-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.QRCode(
        "components_test_qrcode_live",
        "assets/demo-image.png",
        size=160,
    ).allow("content.set", "size.set")
)

builder.add(
    sdk.ui.Button(
        "components_test_qrcode_set_alt_btn",
        "Set alternate",
        action="components.media_test_set",
        params={"component": "qrcode", "state_key": "alternate"},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="qrcode-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: QRCode
  id: components_test_qrcode_yaml_live
  content: "assets/demo-image.png"
  size: 160
  capabilities: [content.set, size.set]
- kind: Button
  id: components_test_qrcode_yaml_set_alt_btn
  label: "Set alternate"
  variant: default
  action: components.media_test_set
  params: {component: qrcode, state_key: alternate}</code></pre></div>
  </div>
</div>

The action must target the current surface when it builds property updates:

```python
surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
sdk.effects.ui_property_update(
    "components_test_qrcode_live",
    "content",
    "WIFI:S:Democrai Demo;T:WPA;P:demo-password;;",
    surface_id=surface_id,
)
```

## Visibility Rules

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="QRCode visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="qrcode-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>show_if = sdk.ui.QRCode(
    "components_test_qrcode_show_if",
    "show_if visible",
    size=140,
)
show_if.set_show_if({
    "conditions": [{
        "left": bound.store("/components_test/visibility/qrcode_show", scope="page", default=True),
        "op": "==",
        "right": True,
    }]
})
builder.add(show_if)

hide_if = sdk.ui.QRCode(
    "components_test_qrcode_hide_if",
    "hide_if visible",
    size=140,
)
hide_if.set_hide_if({
    "conditions": [{
        "left": bound.store("/components_test/visibility/qrcode_hide", scope="page", default=False),
        "op": "==",
        "right": True,
    }]
})
builder.add(hide_if)

gated = sdk.ui.QRCode(
    "components_test_qrcode_required_permissions",
    "required_permissions gate",
    size=140,
)
gated.set_required_permissions(["components.media.visibility"])
builder.add(gated)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="qrcode-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: QRCode
  id: components_test_qrcode_yaml_show_if
  content: "show_if visible"
  size: 140
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/qrcode_show, default: true}
        op: "=="
        right: true
- kind: QRCode
  id: components_test_qrcode_yaml_hide_if
  content: "hide_if visible"
  size: 140
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/qrcode_hide, default: false}
        op: "=="
        right: true
- kind: QRCode
  id: components_test_qrcode_yaml_required_permissions
  content: "required_permissions gate"
  size: 140
  required_permissions: [components.media.visibility]</code></pre></div>
  </div>
</div>

The test page updates the observed store flags with the same action used by Python and YAML declarations:

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="QRCode visibility controls example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-visibility-controls-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="qrcode-visibility-controls-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="qrcode-visibility-controls-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Button(
        "components_test_qrcode_show_off_btn",
        "Hide show_if",
        action="components.media_test_visibility_set",
        params={"component": "qrcode", "flag": "show", "value": False},
        variant="default",
    )
)
builder.add(
    sdk.ui.Button(
        "components_test_qrcode_hide_on_btn",
        "Hide hide_if",
        action="components.media_test_visibility_set",
        params={"component": "qrcode", "flag": "hide", "value": True},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="qrcode-visibility-controls-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: components_test_qrcode_yaml_show_off_btn
  label: "Hide show_if"
  variant: default
  action: components.media_test_visibility_set
  params: {component: qrcode, flag: show, value: false}
- kind: Button
  id: components_test_qrcode_yaml_hide_on_btn
  label: "Hide hide_if"
  variant: default
  action: components.media_test_visibility_set
  params: {component: qrcode, flag: hide, value: true}</code></pre></div>
  </div>
</div>

## Usage Guidance

- Use `content` for the exact string encoded into the QR code.
- Use store bindings when the QR payload follows page or global client state.
- Use data model bindings when the QR payload follows the surface data model.
- Use direct `content` and `size` updates when actions switch payload variants without rebuilding the page.
- Keep foreground and background colors high contrast so the code remains scannable.
