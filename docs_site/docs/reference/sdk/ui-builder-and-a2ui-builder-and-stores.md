# UI Builder and A2UI: Builder and Stores

## Builder

### What it does

`Builder` manages:

- component instances
- surface data model values
- template metadata
- surface serialization into protocol payloads

### Data Model

The builder keeps a per-surface data model in `self._data_model`.

This is the structured payload sent to the client through `dataModelUpdate`. It is not the same thing as the client stores:

- the surface data model is the server-built snapshot attached to one surface
- page/global stores are client-side reactive state used by bindings, visibility rules, and incremental interaction flows

In practice:

- use the data model when the server is preparing the initial surface state or sending a scoped data refresh for that surface
- use page/global stores when the client must react immediately without a full rerender

Example:

```python
builder = sdk.ui.Builder()
builder.set_surface("users_main")
builder.set_data("/filters/search", "anna")
builder.set_data("/filters/status", "active")
builder.set_data("/table/page", 0)
builder.set_data("/table/page_size", 25)
```

This produces a nested data model equivalent to:

```python
{
    "filters": {
        "search": "anna",
        "status": "active",
    },
    "table": {
        "page": 0,
        "page_size": 25,
    },
}
```

### Stores

Store bindings are the reactive client-side layer used by components, conditions, and targeted UI updates.

The common scopes are `page`, for local UI state on the current route or mounted surface, and `global`, for shell-level or cross-navigation state.

The practical distinction is simple: the surface data model is something the server prepares and sends, while stores are values the client keeps alive and reacts to over time. If a text field must keep a draft value, a sidebar item must react to the current path, or a visibility rule must toggle immediately after a client-side update, that belongs in a store rather than in the builder data model.

That is why store bindings show up in visual state such as search drafts, selected tabs, current route highlighting, visibility toggles, and optimistic interaction flows. They are the reactive layer of the rendered UI after the surface has already been mounted.

Programmatically, seed store state with `set_store(...)`, not with `set_data(...)`.

Example:

```python
builder = sdk.ui.Builder()
builder.set_store("/draft_title", "", scope="page")
builder.set_store("/current_path", "/users/index", scope="global")
```

The same idea can be authored programmatically in Python or declared directly in YAML:

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Store bindings">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="stores-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="stores-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="stores-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.Text(
    "draft_value",
    sdk.ui.bound.store("/draft_title", scope="page", default=""),
)

sdk.ui.Text(
    "active_path",
    sdk.ui.bound.store("/current_path", scope="global", default="/"),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="stores-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Text
  id: draft_value
  text: "@state/page/draft_title"

- kind: Text
  id: active_path
  text: "@state/global/current_path"</code></pre></div>
  </div>
</div>

Use the builder when you need to create or patch A2UI payloads. Use stores when the rendered UI must stay reactive after mount.

## A2UI Mapping

In Democr.ai the split is explicit:

- `dataModelUpdate` carries the surface-scoped data model
- `stateUpdate` carries client store values
- `@data/...` reads from the current surface data model
- `@state/...` reads from page/global store

This keeps the A2UI surface data model separate from the client reactive stores.
