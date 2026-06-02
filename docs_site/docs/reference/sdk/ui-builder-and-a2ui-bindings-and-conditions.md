# UI Builder and A2UI: Bindings and Conditions

## Bound Helpers

The UI builder layer re-exports:

- `ActionBoundValue`
- `LiteralValue`
- `bound`
- `Condition`

These helpers exist because this project supports more than one binding style, depending on where the UI is authored.

In Python render code, the most explicit form is the factory API under `sdk.ui.bound`. That is the low-level shape used to declare a store-bound value, a data-model bound value, an action-bound value, or an explicit literal.

`ActionBoundValue(...)` is the shorthand for a client value loaded through an action instead of read from store state. `LiteralValue(...)` does the same for plain literals when you want to be explicit instead of relying on implicit string handling.

In YAML, the same ideas are exposed through compact strings such as `@state/page/...`, `@state/global/...`, `@state/...`, `@data/...`, `@action/...`, `@literal/...`, and `@t/...`, or through the equivalent explicit object form with `type`, `path`, `scope`, `args`, and `default`.

Use a store-bound form when the client should read reactive state. Use a data-bound form when the component should read from the current surface data model. Use an action-bound form when the value should be computed or loaded lazily by invoking an action. Use a literal form when the content must remain plain text even if it resembles binding syntax.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Binding forms">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="bindings-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="bindings-yaml" aria-selected="false">YAML</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="bindings-yaml-explicit" aria-selected="false">Explicit YAML</button>
  </div>
  <div class="docs-code-group__panel" id="bindings-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.bound.store("/draft_title", scope="page", default="")
sdk.ui.bound("/draft_title", scope="page", default="")
sdk.ui.bound.data("/filters/search", default="")
sdk.ui.bound.action("demo.users.count", args={"status": "active"}, default=0)
sdk.ui.ActionBoundValue("demo.users.count", args={"status": "active"}, default=0)
sdk.ui.bound.literal("Dashboard")
sdk.ui.LiteralValue("Dashboard")</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="bindings-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>text: "@state/page/draft_title"
text: "@state/global/current_path"
text: "@state/draft_title"
text: "@data/filters/search"
text: "@action/demo.users.count"
text: "@literal/@state/page/not_a_binding"
text: "@t/system.user.list.title"</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="bindings-yaml-explicit" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>text:
  type: store
  scope: page
  path: /draft_title
  default: ""

text:
  path: /filters/search
  default: ""

text:
  type: action
  name: demo.users.count
  args:
    status: active
  default: 0
  cache_scope: page

text:
  type: literal
  value: "Dashboard"</code></pre></div>
  </div>
</div>

For YAML, the compact form and the explicit object form are equivalent. The important distinction is:

- `type: store` or `@state/...` means client store binding
- bare `path` or `@data/...` means surface data-model binding

Examples:

```python
sdk.ui.bound.literal("Dashboard")
sdk.ui.bound.store("/draft_title", scope="page", default="")
sdk.ui.bound("/draft_title", scope="page", default="")
sdk.ui.bound.data("/filters/search", default="")
sdk.ui.bound.action("demo.users.count", args={"status": "active"}, default=0)
sdk.ui.ActionBoundValue("demo.users.count", args={"status": "active"}, default=0)
sdk.ui.Condition.AND(
    sdk.ui.Condition(
        sdk.ui.bound.store("/current_path", scope="global", default="/"),
        "==",
        "/demo/users",
    )
)
```
