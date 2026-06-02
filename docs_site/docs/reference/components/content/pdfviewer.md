# PdfViewer

[<- Back to Content Components](./index.md)

`PdfViewer` renders a PDF document with a download action. Use it when a module page must show packaged PDF assets, runtime media URLs, store-driven document previews, or desktop attachment payloads resolved by `file_id`.

On desktop the primary renderer uses the native Qt PDF view with multipage scrolling, fit-to-width, zoom controls, page navigation, and optional page thumbnails. If Qt PDF support is not available, the desktop client falls back to the PDF preview renderer. On web, the component renders the resolved document source in an iframe.

## Python Contract

```python
sdk.ui.PdfViewer(
    id: str,
    name: Any = "",
    source_path: Any = "",
    file_id: str = "",
    url: Any = "",
    height: Any = 520,
    fit: str = "",
)
```

`name`, `source_path`, `url`, and `height` accept literal values or bindings from the constructor. `file_id` is a literal desktop lookup identifier.

## Supported Properties

| Property | Type | Required | Python | YAML | Notes |
|---|---|---|---|---|---|
| `id` | `str` | yes | yes | yes | Stable component id |
| `name` | `str | binding` | no | constructor / `name.set` | yes | Download filename and document label |
| `source_path` | `str | binding` | no | constructor / `source_path.set` | yes | Preferred source for module assets or runtime media paths |
| `file_id` | `str` | no | constructor / `file_id.set` | yes | Desktop attachment lookup identifier |
| `url` | `str | binding` | no | constructor / `url.set` | yes | Alternate source when `source_path` is empty |
| `height` | `int | binding` | no | constructor / `height.set` | yes | Minimum viewer height; default `520` |
| `fit` | `str` | no | constructor / `fit.set` | yes | Desktop uses `container` as fit-to-width |
| `show_if` | rule | no | yes | yes | Generic visibility rule |
| `hide_if` | rule | no | yes | yes | Generic visibility rule |
| `required_permissions` | `list[str]` | no | yes | yes | Generic permission gate |

## Source Selection

- Web resolves the first non-empty source between `source_path` and `url`.
- Desktop resolves the same source and can also load bytes through `file_id`.
- If no usable source resolves to a client URL or PDF payload, the renderer shows its unavailable-source placeholder.

## Static Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="PdfViewer static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.PdfViewer(
        "report_pdf",
        name="Quarterly report",
        source_path="assets/test.pdf",
        height=360,
        fit="container",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: PdfViewer
  id: report_pdf_yaml
  name: "Quarterly report"
  source_path: "assets/test.pdf"
  height: 360
  fit: container</code></pre></div>
  </div>
</div>

## Store Binding

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="PdfViewer store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.PdfViewer(
        "report_pdf_store",
        name=bound.store("/documents/current_pdf/name", scope="page", default="Quarterly report"),
        source_path=bound.store("/documents/current_pdf/source_path", scope="page", default="assets/test.pdf"),
        url=bound.store("/documents/current_pdf/url", scope="page", default=""),
        height=bound.store("/documents/current_pdf/height", scope="page", default=360),
        fit="container",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: PdfViewer
  id: report_pdf_yaml_store
  name: {type: store, scope: page, path: /documents/current_pdf/name, default: "Quarterly report"}
  source_path: {type: store, scope: page, path: /documents/current_pdf/source_path, default: "assets/test.pdf"}
  url: {type: store, scope: page, path: /documents/current_pdf/url, default: ""}
  height: {type: store, scope: page, path: /documents/current_pdf/height, default: 360}
  fit: container</code></pre></div>
  </div>
</div>

## Data Model Binding

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="PdfViewer data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.PdfViewer(
        "report_pdf_data",
        name=bound.data("/documents/current_pdf_model/name", default="Quarterly report"),
        source_path=bound.data("/documents/current_pdf_model/source_path", default="assets/test.pdf"),
        url=bound.data("/documents/current_pdf_model/url", default=""),
        height=bound.data("/documents/current_pdf_model/height", default=360),
        fit="container",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: PdfViewer
  id: report_pdf_yaml_data
  name: "@data/documents/current_pdf_model/name"
  source_path: "@data/documents/current_pdf_model/source_path"
  url: "@data/documents/current_pdf_model/url"
  height: "@data/documents/current_pdf_model/height"
  fit: container</code></pre></div>
  </div>
</div>

## Direct Property Update

Declare update capabilities before an action sends `propertyUpdate` messages.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="PdfViewer property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.PdfViewer(
        "report_pdf_live",
        name="Quarterly report",
        source_path="assets/test.pdf",
        height=360,
        fit="container",
    ).allow("name.set", "source_path.set", "url.set", "height.set")
)

builder.add(
    sdk.ui.Button(
        "report_pdf_set_alt_btn",
        "Show alternate PDF",
        action="documents.set_pdf_variant",
        params={"variant": "alternate"},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: PdfViewer
  id: report_pdf_yaml_live
  name: "Quarterly report"
  source_path: "assets/test.pdf"
  height: 360
  fit: container
  capabilities: [name.set, source_path.set, url.set, height.set]
- kind: Button
  id: report_pdf_yaml_set_alt_btn
  label: "Show alternate PDF"
  variant: default
  action: documents.set_pdf_variant
  params: {variant: alternate}</code></pre></div>
  </div>
</div>

The action targets the current surface when it sends direct property updates:

```python
surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
sdk.effects.ui_property_update(
    "report_pdf_live",
    "source_path",
    "assets/test2.pdf",
    surface_id=surface_id,
)
```

## Visibility Rules

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="PdfViewer visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>show_if = sdk.ui.PdfViewer(
    "report_pdf_show_if",
    name="Visible report",
    source_path="assets/test.pdf",
    height=320,
    fit="container",
)
show_if.set_show_if({
    "conditions": [{
        "left": bound.store("/documents/pdf_viewer_visibility/show", scope="page", default=True),
        "op": "==",
        "right": True,
    }]
})
builder.add(show_if)

hide_if = sdk.ui.PdfViewer(
    "report_pdf_hide_if",
    name="Hideable report",
    source_path="assets/test.pdf",
    height=320,
    fit="container",
)
hide_if.set_hide_if({
    "conditions": [{
        "left": bound.store("/documents/pdf_viewer_visibility/hide", scope="page", default=False),
        "op": "==",
        "right": True,
    }]
})
builder.add(hide_if)

gated = sdk.ui.PdfViewer(
    "report_pdf_required_permissions",
    name="Permission-gated report",
    source_path="assets/test.pdf",
    height=320,
    fit="container",
)
gated.set_required_permissions(["documents.view_pdf"])
builder.add(gated)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: PdfViewer
  id: report_pdf_yaml_show_if
  name: "Visible report"
  source_path: "assets/test.pdf"
  height: 320
  fit: container
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /documents/pdf_viewer_visibility/show, default: true}
        op: "=="
        right: true
- kind: PdfViewer
  id: report_pdf_yaml_hide_if
  name: "Hideable report"
  source_path: "assets/test.pdf"
  height: 320
  fit: container
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /documents/pdf_viewer_visibility/hide, default: false}
        op: "=="
        right: true
- kind: PdfViewer
  id: report_pdf_yaml_required_permissions
  name: "Permission-gated report"
  source_path: "assets/test.pdf"
  height: 320
  fit: container
  required_permissions: [documents.view_pdf]</code></pre></div>
  </div>
</div>

A visibility action can update the same store flags:

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="PdfViewer visibility controls example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-visibility-controls-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="pdfviewer-visibility-controls-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-visibility-controls-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Button(
        "report_pdf_hide_show_rule_btn",
        "Hide conditional PDF",
        action="documents.set_pdf_visibility",
        params={"flag": "show", "value": False},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="pdfviewer-visibility-controls-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: report_pdf_yaml_hide_show_rule_btn
  label: "Hide conditional PDF"
  variant: default
  action: documents.set_pdf_visibility
  params: {flag: show, value: false}</code></pre></div>
  </div>
</div>

## Path Resolution

- Module asset paths such as `assets/test.pdf` and `assets/test2.pdf` resolve to the media route for the active module.
- `assets/protected/...` resolves to the same module media route but requires an authenticated user before the file is served.
- `/media/...` is already a client-facing media path and is used as-is by the clients.
- `http://...` and `https://...` are external URLs. On web they are resolved through the media proxy when they are outside the core origin.

## Usage Guidance

- Use `source_path="assets/test.pdf"` for packaged module documents.
- Use store bindings when the selected PDF follows page or global client state.
- Use data model bindings when the viewer follows the surface data model.
- Use direct updates for document switching without a full page rerender.
- Use `url` only when the document source is already an external or runtime URL and `source_path` is empty.
- Use `fit="container"` when the desktop viewer should start in fit-to-width mode.
