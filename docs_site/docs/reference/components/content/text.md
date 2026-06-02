# Text

[<- Back to Content Components](./index.md)

`Text` renders plain copy, helper descriptions, status lines, and other paragraph-level content. Use it when no Markdown formatting is required.

## Python Contract

```python
sdk.ui.Text(
    id: str,
    text: Any,
)
```

`text` accepts literal values, store bindings, and data-model bindings from the constructor.

## Supported Properties

| Property | Type | Required | Python | YAML | Desktop | Web | Notes |
|---|---|---|---|---|---|---|---|
| `id` | `str` | yes | yes | yes | yes | yes | Stable component id |
| `text` | scalar or binding | yes | constructor / `text.set` | yes | yes | yes | Plain text content |
| `align` | str or binding | no | `set_property` / `align.set` | yes | yes | yes | `left`, `center`, `right` |
| `selectable` | bool | no | `set_property` / `selectable.set` | yes | yes | yes | Enables text selection |
| `muted` | bool | no | via `set_property` | yes | no | yes | Web-only muted styling |
| `tone` | str | no | via `set_property` | yes | no | yes | Web accepts `default`, `muted`, `secondary` |
| `style` | str | no | yes | yes | yes | yes | Inline style string |
| `show_if` | rule | no | yes | yes | yes | yes | Generic visibility contract |
| `hide_if` | rule | no | yes | yes | yes | yes | Generic visibility contract |
| `required_permissions` | list[str] | no | yes | yes | yes | yes | Generic permission gate |

## Binding Paths

The component test page uses these paths:

- Store: `/components_test/text/text`, `/components_test/text/align`
- Data model: `/components_test/text_model/text`, `/components_test/text_model/align`
- Visibility store: `/components_test/visibility/text_show`, `/components_test/visibility/text_hide`

## Static Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Text static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="text-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Text(
        "components_test_text_static",
        "Static plain text.",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="text-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Text
  id: components_test_text_yaml_static
  text: "Static plain text."</code></pre></div>
  </div>
</div>

## Store Binding Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Text store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="text-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

text = sdk.ui.Text(
    "components_test_text_store",
    bound.store(
        "/components_test/text/text",
        scope="page",
        default="Store-bound body copy.",
    ),
)
text.set_property(
    "align",
    bound.store(
        "/components_test/text/align",
        scope="page",
        default="left",
    ),
)
builder.add(text)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="text-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Text
  id: components_test_text_yaml_store
  text:
    type: store
    scope: page
    path: /components_test/text/text
    default: "Store-bound body copy."
  align:
    type: store
    scope: page
    path: /components_test/text/align
    default: left</code></pre></div>
  </div>
</div>

## Data Model Binding Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Text data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="text-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>text = sdk.ui.Text(
    "components_test_text_data",
    bound.data(
        "/components_test/text_model/text",
        default="Data-model body copy.",
    ),
)
text.set_property(
    "align",
    bound.data(
        "/components_test/text_model/align",
        default="center",
    ),
)
builder.add(text)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="text-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Text
  id: components_test_text_yaml_data
  text: "@data/components_test/text_model/text"
  align: "@data/components_test/text_model/align"</code></pre></div>
  </div>
</div>

## Runtime Property Update Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Text runtime update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-runtime-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-runtime-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="text-runtime-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Text(
        "components_test_text_live",
        "Runtime text.",
    ).allow("text.set", "align.set")
)

builder.add(
    sdk.ui.Button(
        "components_test_text_set_alt_btn",
        "Set alternate",
        action="components.content_test_set",
        params={"component": "text", "state_key": "alternate"},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="text-runtime-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Text
  id: components_test_text_yaml_live
  text: "Runtime text."
  capabilities: [text.set, align.set]

- kind: Button
  id: components_test_text_yaml_set_alt_btn
  label: "Set alternate"
  variant: default
  action: components.content_test_set
  params: {component: text, state_key: alternate}</code></pre></div>
  </div>
</div>

The action targets the current surface when it sends direct property updates:

```python
surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
return sdk.effects.respond(
    sdk.effects.ui_property_update(
        "components_test_text_live",
        "text",
        "Updated runtime text.",
        surface_id=surface_id,
    ),
    sdk.effects.ui_property_update(
        "components_test_text_live",
        "align",
        "center",
        surface_id=surface_id,
    ),
)
```

## Visibility And Permissions Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Text visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="text-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="text-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>text = sdk.ui.Text(
    "components_test_text_show_if",
    "show_if visible",
)
text.set_show_if({
    "conditions": [
        {
            "left": bound.store(
                "/components_test/visibility/text_show",
                scope="page",
                default=True,
            ),
            "op": "==",
            "right": True,
        }
    ]
})
builder.add(text)

gated = sdk.ui.Text(
    "components_test_text_required_permissions",
    "required_permissions gate",
)
gated.set_required_permissions(["components.content.visibility"])
builder.add(gated)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="text-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Text
  id: components_test_text_yaml_show_if
  text: "show_if visible"
  show_if:
    conditions:
      - left:
          type: store
          scope: page
          path: /components_test/visibility/text_show
          default: true
        op: "=="
        right: true

- kind: Text
  id: components_test_text_yaml_hide_if
  text: "hide_if visible"
  hide_if:
    conditions:
      - left:
          type: store
          scope: page
          path: /components_test/visibility/text_hide
          default: false
        op: "=="
        right: true

- kind: Text
  id: components_test_text_yaml_required_permissions
  text: "required_permissions gate"
  required_permissions: [components.content.visibility]</code></pre></div>
  </div>
</div>

Use an action to change the observed store flags:

```python
return sdk.effects.respond(
    sdk.effects.ui_messages([
        {
            "stateUpdate": {
                "scope": "page",
                "values": {
                    "/components_test/visibility/text_hide": True,
                },
            }
        }
    ])
)
```

## Usage Guidance

- Use `Text` for paragraph-level copy, helper text, and small status lines.
- Bind `text` from the constructor when the value follows store or data-model state.
- Declare `text.set` and `align.set` capabilities when direct property updates target the component.
- Use `show_if`, `hide_if`, and `required_permissions` for visibility and authorization gates.
