# Status & Badges

[<- Back to Content Components](./index.md)

`Badge` and `Alert` render status information inside a module page. Use `Badge` for compact inline status, counters, or tags. Use `Alert` for an expanded status block with title, description, and visual variant.

There is no separate `Status` SDK component in the current contract. The expanded status example uses `sdk.ui.Alert`.

## Variants

| Component | Supported variants |
|---|---|
| `Badge` | `default`, `success`, `warning`, `destructive` |
| `Alert` | `info`, `success`, `warning`, `destructive`, `default` |

The web renderer also recognises `info` on `Badge` as an additional variant class. Unknown variant values fall back to the component default.

## Badge Contract

```python
sdk.ui.Badge(
    id: str,
    text: Any,
    variant: Any = "default",
)
```

`text` and `variant` accept literal values, store bindings, and data-model bindings from the constructor.

| Property | Type | Required | Python | YAML | Desktop | Web | Notes |
|---|---|---|---|---|---|---|---|
| `id` | `str` | yes | yes | yes | yes | yes | Stable component id |
| `text` | scalar or binding | yes | constructor / `text.set` / `text.append` | yes | yes | yes | Label rendered inside the badge |
| `variant` | str or binding | no | constructor / `variant.set` | yes | yes | yes | Visual variant |
| `style` | str | no | yes | yes | yes | yes | Inline style string |
| `show_if` | rule | no | yes | yes | yes | yes | Generic visibility contract |
| `hide_if` | rule | no | yes | yes | yes | yes | Generic visibility contract |
| `required_permissions` | list[str] | no | yes | yes | yes | yes | Generic permission gate |

## Alert Contract

```python
sdk.ui.Alert(
    id: str,
    title: Any,
    description: Any = "",
    variant: Any = "info",
)
```

`title`, `description`, and `variant` accept literal values, store bindings, and data-model bindings from the constructor.

| Property | Type | Required | Python | YAML | Desktop | Web | Notes |
|---|---|---|---|---|---|---|---|
| `id` | `str` | yes | yes | yes | yes | yes | Stable component id |
| `title` | scalar or binding | yes | constructor / `title.set` | yes | yes | yes | Alert headline |
| `description` | scalar or binding | no | constructor / `description.set` | yes | yes | yes | Desktop hides the body label when empty |
| `variant` | str or binding | no | constructor / `variant.set` | yes | yes | yes | Visual variant |
| `style` | str | no | yes | yes | yes | yes | Inline style string |
| `show_if` | rule | no | yes | yes | yes | yes | Generic visibility contract |
| `hide_if` | rule | no | yes | yes | yes | yes | Generic visibility contract |
| `required_permissions` | list[str] | no | yes | yes | yes | yes | Generic permission gate |

## Binding Paths

The component test page uses these paths:

- Badge store: `/components_test/badge/text`, `/components_test/badge/variant`
- Badge data model: `/components_test/badge_model/text`, `/components_test/badge_model/variant`
- Alert store: `/components_test/status/title`, `/components_test/status/description`, `/components_test/status/variant`
- Alert data model: `/components_test/status_model/title`, `/components_test/status_model/description`, `/components_test/status_model/variant`
- Visibility store: `/components_test/visibility/badge_show`, `/components_test/visibility/badge_hide`, `/components_test/visibility/status_show`, `/components_test/visibility/status_hide`

## Static Examples

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Status static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="status-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Badge(
        "components_test_badge_static",
        "Static badge",
        variant="default",
    )
)

builder.add(
    sdk.ui.Alert(
        "components_test_status_static",
        "Static status",
        "Literal status message.",
        variant="info",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="status-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Badge
  id: components_test_badge_yaml_static
  text: "Static badge"
  variant: default

- kind: Alert
  id: components_test_status_yaml_static
  title: "Static status"
  description: "Literal status message."
  variant: info</code></pre></div>
  </div>
</div>

## Store Binding Examples

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Status store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="status-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.Badge(
        "components_test_badge_store",
        bound.store(
            "/components_test/badge/text",
            scope="page",
            default="Store badge",
        ),
        variant=bound.store(
            "/components_test/badge/variant",
            scope="page",
            default="default",
        ),
    )
)

builder.add(
    sdk.ui.Alert(
        "components_test_status_store",
        bound.store(
            "/components_test/status/title",
            scope="page",
            default="Store-bound status",
        ),
        bound.store(
            "/components_test/status/description",
            scope="page",
            default="Status follows page store.",
        ),
        variant=bound.store(
            "/components_test/status/variant",
            scope="page",
            default="info",
        ),
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="status-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Badge
  id: components_test_badge_yaml_store
  text:
    type: store
    scope: page
    path: /components_test/badge/text
    default: "Store badge"
  variant:
    type: store
    scope: page
    path: /components_test/badge/variant
    default: default

- kind: Alert
  id: components_test_status_yaml_store
  title:
    type: store
    scope: page
    path: /components_test/status/title
    default: "Store-bound status"
  description:
    type: store
    scope: page
    path: /components_test/status/description
    default: "Status follows page store."
  variant:
    type: store
    scope: page
    path: /components_test/status/variant
    default: info</code></pre></div>
  </div>
</div>

## Data Model Binding Examples

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Status data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="status-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Badge(
        "components_test_badge_data",
        bound.data(
            "/components_test/badge_model/text",
            default="Data badge",
        ),
        variant=bound.data(
            "/components_test/badge_model/variant",
            default="success",
        ),
    )
)

builder.add(
    sdk.ui.Alert(
        "components_test_status_data",
        bound.data(
            "/components_test/status_model/title",
            default="Data-model status",
        ),
        bound.data(
            "/components_test/status_model/description",
            default="Status follows the surface data model.",
        ),
        variant=bound.data(
            "/components_test/status_model/variant",
            default="success",
        ),
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="status-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Badge
  id: components_test_badge_yaml_data
  text: "@data/components_test/badge_model/text"
  variant: "@data/components_test/badge_model/variant"

- kind: Alert
  id: components_test_status_yaml_data
  title: "@data/components_test/status_model/title"
  description: "@data/components_test/status_model/description"
  variant: "@data/components_test/status_model/variant"</code></pre></div>
  </div>
</div>

## Runtime Property Update Examples

Both components expose runtime capabilities from the constructor. The YAML examples still declare the direct-update capabilities explicitly so the page test shows the component contract at the call site.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Status runtime update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-runtime-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-runtime-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="status-runtime-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Badge(
        "components_test_badge_live",
        "Runtime badge",
        variant="default",
    )
)

builder.add(
    sdk.ui.Alert(
        "components_test_status_live",
        "Runtime status",
        "Default runtime message.",
        variant="info",
    )
)

builder.add(
    sdk.ui.Button(
        "components_test_badge_set_alt_btn",
        "Set alternate",
        action="components.content_test_set",
        params={"component": "badge", "state_key": "alternate"},
        variant="default",
    )
)

builder.add(
    sdk.ui.Button(
        "components_test_status_set_alt_btn",
        "Set alternate",
        action="components.content_test_set",
        params={"component": "status", "state_key": "alternate"},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="status-runtime-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Badge
  id: components_test_badge_yaml_live
  text: "Runtime badge"
  variant: default
  capabilities: [text.set, variant.set]

- kind: Alert
  id: components_test_status_yaml_live
  title: "Runtime status"
  description: "Default runtime message."
  variant: info
  capabilities: [title.set, description.set, variant.set]

- kind: Button
  id: components_test_badge_yaml_set_alt_btn
  label: "Set alternate"
  variant: default
  action: components.content_test_set
  params: {component: badge, state_key: alternate}

- kind: Button
  id: components_test_status_yaml_set_alt_btn
  label: "Set alternate"
  variant: default
  action: components.content_test_set
  params: {component: status, state_key: alternate}</code></pre></div>
  </div>
</div>

The action sends updates to the current surface:

```python
surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
return sdk.effects.respond(
    sdk.effects.ui_property_update(
        "components_test_badge_live",
        "text",
        "Updated badge",
        surface_id=surface_id,
    ),
    sdk.effects.ui_property_update(
        "components_test_badge_live",
        "variant",
        "success",
        surface_id=surface_id,
    ),
    sdk.effects.ui_property_update(
        "components_test_status_live",
        "title",
        "Updated status",
        surface_id=surface_id,
    ),
    sdk.effects.ui_property_update(
        "components_test_status_live",
        "description",
        "The status changed from the action.",
        surface_id=surface_id,
    ),
    sdk.effects.ui_property_update(
        "components_test_status_live",
        "variant",
        "success",
        surface_id=surface_id,
    ),
)
```

## Visibility And Permissions Examples

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Status visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="status-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="status-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>badge = sdk.ui.Badge(
    "components_test_badge_show_if",
    "show_if visible",
    variant="warning",
)
badge.set_show_if({
    "conditions": [
        {
            "left": bound.store(
                "/components_test/visibility/badge_show",
                scope="page",
                default=True,
            ),
            "op": "==",
            "right": True,
        }
    ]
})
builder.add(badge)

alert = sdk.ui.Alert(
    "components_test_status_hide_if",
    "hide_if visible",
    "Visibility rule target.",
    variant="warning",
)
alert.set_hide_if({
    "conditions": [
        {
            "left": bound.store(
                "/components_test/visibility/status_hide",
                scope="page",
                default=False,
            ),
            "op": "==",
            "right": True,
        }
    ]
})
builder.add(alert)

gated_badge = sdk.ui.Badge(
    "components_test_badge_required_permissions",
    "required_permissions gate",
    variant="default",
)
gated_badge.set_required_permissions(["components.content.visibility"])
builder.add(gated_badge)

gated_alert = sdk.ui.Alert(
    "components_test_status_required_permissions",
    "required_permissions gate",
    "Permission-gated status.",
    variant="info",
)
gated_alert.set_required_permissions(["components.content.visibility"])
builder.add(gated_alert)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="status-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Badge
  id: components_test_badge_yaml_show_if
  text: "show_if visible"
  variant: warning
  show_if:
    conditions:
      - left:
          type: store
          scope: page
          path: /components_test/visibility/badge_show
          default: true
        op: "=="
        right: true

- kind: Badge
  id: components_test_badge_yaml_hide_if
  text: "hide_if visible"
  variant: warning
  hide_if:
    conditions:
      - left:
          type: store
          scope: page
          path: /components_test/visibility/badge_hide
          default: false
        op: "=="
        right: true

- kind: Alert
  id: components_test_status_yaml_show_if
  title: "show_if visible"
  description: "Visibility rule target."
  variant: warning
  show_if:
    conditions:
      - left:
          type: store
          scope: page
          path: /components_test/visibility/status_show
          default: true
        op: "=="
        right: true

- kind: Alert
  id: components_test_status_yaml_hide_if
  title: "hide_if visible"
  description: "Visibility rule target."
  variant: warning
  hide_if:
    conditions:
      - left:
          type: store
          scope: page
          path: /components_test/visibility/status_hide
          default: false
        op: "=="
        right: true

- kind: Badge
  id: components_test_badge_yaml_required_permissions
  text: "required_permissions gate"
  variant: default
  required_permissions: [components.content.visibility]

- kind: Alert
  id: components_test_status_yaml_required_permissions
  title: "required_permissions gate"
  description: "Permission-gated status."
  variant: info
  required_permissions: [components.content.visibility]</code></pre></div>
  </div>
</div>

Use `components.content_test_visibility_set` or the same `stateUpdate` shape to change the page-store flags observed by `show_if` and `hide_if`.

## Usage Guidance

- Use `Badge` when the status fits in a compact inline label.
- Use `Alert` when the message needs a title plus an explanation.
- Bind constructor values when status text or variant follows store or data-model state.
- Use direct property updates when a single visible component should change without a full render.
- Use `show_if`, `hide_if`, and `required_permissions` for visibility and authorization gates.
