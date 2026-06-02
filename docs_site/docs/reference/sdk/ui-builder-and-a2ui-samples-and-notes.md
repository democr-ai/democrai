# UI Builder and A2UI: Samples and Notes

## Full Sample

This comparison is useful when deciding whether a surface should stay YAML-first or whether it needs programmatic assembly in the render function. The YAML version is shorter and easier to scan when the structure is static. The Python version is the right tool when the surface shape itself is computed.

One important constraint matters here: the current YAML loader supports the surface structure itself, but it does not currently read builder-only root sections such as a declarative `data_model` or page/global store seed. If your surface needs initial `set_data(...)` or `set_store(...)`, load the YAML first and then seed those values from Python.

The same caution applies to `template`: the loader accepts it, but for most module UI that value is usually chosen by the render flow that prepares the surface, not by a minimal YAML fragment. In a small YAML-only example, including `template: full` often creates more confusion than value.

The same is true for root `surface_id`. It does not identify one component. It binds the whole builder to one target surface, which is a different concern from component ids such as `title`. In a minimal sample, it is usually clearer to keep component ids in YAML and keep the surface binding in Python.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Full sample">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="full-sample-python" data-active="true" aria-selected="true">Python Builder</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="full-sample-yaml" aria-selected="false">YAML First</button>
  </div>
  <div class="docs-code-group__panel" id="full-sample-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder = sdk.ui.Builder()
builder.set_template("full", session=session)
builder.set_surface("users_main")
builder.set_data("/filters/search", "Users")
builder.set_store("/drafts/search", "", scope="page")
builder.add(
    sdk.ui.Text(
        "title",
        sdk.ui.bound.data("/filters/search", default=""),
    )
)
payload = builder.build_surface_update_payload("users_main")</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="full-sample-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>components:
  - kind: Text
    id: title
    text: "@data/filters/search"</code></pre></div>
    <div class="language-python highlight"><pre><code>builder = sdk.ui.load("ui/yaml/users_main")
builder.set_surface("users_main")
builder.set_template("full", session=session)
builder.set_data("/filters/search", "Users")
payload = builder.build_surface_update_payload(builder.surface_id)</code></pre></div>
  </div>
</div>

## Practical Notes

- `Builder` is part of the `ui` domain, not a separate root-level SDK shortcut.
- Use `Builder` directly when the UI cannot be expressed entirely through YAML.
- The current YAML loader understands root keys such as `template`, `surface_id`, and `components`, but not a declarative root `data_model` or builder store seed.
- Root `surface_id` is the target surface of the builder, not the `id` of one component. Keep those concepts separate in examples and in real code.
- In practice, keep structural UI in YAML and keep builder concerns such as `set_surface(...)`, `set_template(...)`, `set_data(...)`, and `set_store(...)` in the Python render flow unless the YAML file genuinely needs to carry them.
- When you load YAML with `sdk.ui.load(...)`, prefer putting structural UI in YAML and then calling `set_data(...)` / `set_store(...)` from Python for runtime state initialization.
- Treat the builder data model as surface-scoped server state, not as a replacement for page/global stores.
- Prefer page/global stores for reactive UI state that should update without rebuilding the full surface.
- Use `set_data(...)` for surface data model and `set_store(...)` for page/global client state.
- Use `@data/...` for surface data model bindings and `@state/...` for store bindings.
- Prefer targeted property and collection updates over full surface rebuilds when the structure is already mounted.
- Pair this layer with `sdk.effects` for action responses.

