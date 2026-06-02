# Video

[<- Back to Content Components](./index.md)

`Video` renders a video player for module assets, runtime media URLs, proxied external URLs, or other client-safe video sources. Use it when the interface must play clips with optional title and poster artwork.

## Python Contract

```python
sdk.ui.Video(
    id: str,
    source: Any = "",
    title: Any = "",
    autoplay: bool = False,
    muted: bool = False,
    loop: bool = False,
    controls: bool = True,
    poster: Any = "",
    width: int = 640,
    height: int = 360,
)
```

`source`, `title`, and `poster` accept literal values or bindings from the constructor.

## Supported Properties

| Property | Type | Required | Python | YAML | Notes |
|---|---|---|---|---|---|
| `id` | `str` | yes | yes | yes | Stable component id |
| `source` | `str | binding` | no | constructor / `source.set` | yes | Video source URL or module asset path |
| `title` | `str | binding` | no | constructor / `title.set` | yes | Visible player label |
| `autoplay` | `bool` | no | constructor / `autoplay.set` | yes | Starts playback automatically when allowed by the client |
| `muted` | `bool` | no | constructor / `muted.set` | yes | Starts muted |
| `loop` | `bool` | no | constructor / `loop.set` | yes | Replays after end of track |
| `controls` | `bool` | no | constructor | yes | Hides or shows playback controls |
| `poster` | `str | binding` | no | constructor / `poster.set` | yes | Optional image shown before playback |
| `width` | `int` | no | constructor | yes | Default `640` |
| `height` | `int` | no | constructor | yes | Default `360` |
| `show_if` | rule | no | yes | yes | Generic visibility rule |
| `hide_if` | rule | no | yes | yes | Generic visibility rule |
| `required_permissions` | `list[str]` | no | yes | yes | Generic permission gate |

## Static Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Video static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="video-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Video(
        "components_test_video_static",
        source="assets/test.mp4",
        title="Flower MP4",
        controls=True,
        width=360,
        height=210,
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="video-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Video
  id: components_test_video_yaml_static
  source: "assets/test.mp4"
  title: "Flower MP4"
  controls: true
  width: 360
  height: 210</code></pre></div>
  </div>
</div>

## Store Binding

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Video store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="video-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.Video(
        "components_test_video_store",
        source=bound.store("/components_test/video/source", scope="page", default="assets/test.mp4"),
        title=bound.store("/components_test/video/title", scope="page", default="Flower MP4"),
        poster=bound.store("/components_test/video/poster", scope="page", default=""),
        controls=True,
        width=360,
        height=210,
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="video-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Video
  id: components_test_video_yaml_store
  source: {type: store, scope: page, path: /components_test/video/source, default: "assets/test.mp4"}
  title: {type: store, scope: page, path: /components_test/video/title, default: "Flower MP4"}
  poster: {type: store, scope: page, path: /components_test/video/poster, default: ""}
  controls: true
  width: 360
  height: 210</code></pre></div>
  </div>
</div>

## Data Model Binding

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Video data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="video-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

builder.add(
    sdk.ui.Video(
        "components_test_video_data",
        source=bound.data("/components_test/video_model/source", default="assets/test.mp4"),
        title=bound.data("/components_test/video_model/title", default="Flower MP4"),
        poster=bound.data("/components_test/video_model/poster", default=""),
        controls=True,
        width=360,
        height=210,
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="video-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Video
  id: components_test_video_yaml_data
  source: "@data/components_test/video_model/source"
  title: "@data/components_test/video_model/title"
  poster: "@data/components_test/video_model/poster"
  controls: true
  width: 360
  height: 210</code></pre></div>
  </div>
</div>

## Direct Property Update

Declare `source.set`, `title.set`, and `poster.set` before an action sends direct updates to the rendered player.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Video property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="video-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Video(
        "components_test_video_live",
        source="assets/test.mp4",
        title="Flower MP4",
        controls=True,
        width=360,
        height=210,
    ).allow("source.set", "title.set", "poster.set")
)

builder.add(
    sdk.ui.Button(
        "components_test_video_set_alt_btn",
        "Set alternate",
        action="components.media_test_set",
        params={"component": "video", "state_key": "alternate"},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="video-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Video
  id: components_test_video_yaml_live
  source: "assets/test.mp4"
  title: "Flower MP4"
  controls: true
  width: 360
  height: 210
  capabilities: [source.set, title.set, poster.set]
- kind: Button
  id: components_test_video_yaml_set_alt_btn
  label: "Set alternate"
  variant: default
  action: components.media_test_set
  params: {component: video, state_key: alternate}</code></pre></div>
  </div>
</div>

The action must target the current surface when it builds property updates:

```python
surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
sdk.effects.ui_property_update(
    "components_test_video_live",
    "source",
    "assets/test2.mp4",
    surface_id=surface_id,
)
```

## Visibility Rules

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Video visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="video-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>show_if = sdk.ui.Video(
    "components_test_video_show_if",
    source="assets/test.mp4",
    title="show_if visible",
    width=320,
    height=190,
)
show_if.set_show_if({
    "conditions": [{
        "left": bound.store("/components_test/visibility/video_show", scope="page", default=True),
        "op": "==",
        "right": True,
    }]
})
builder.add(show_if)

hide_if = sdk.ui.Video(
    "components_test_video_hide_if",
    source="assets/test.mp4",
    title="hide_if visible",
    width=320,
    height=190,
)
hide_if.set_hide_if({
    "conditions": [{
        "left": bound.store("/components_test/visibility/video_hide", scope="page", default=False),
        "op": "==",
        "right": True,
    }]
})
builder.add(hide_if)

gated = sdk.ui.Video(
    "components_test_video_required_permissions",
    source="assets/test.mp4",
    title="required_permissions gate",
    width=320,
    height=190,
)
gated.set_required_permissions(["components.media.visibility"])
builder.add(gated)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="video-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Video
  id: components_test_video_yaml_show_if
  source: "assets/test.mp4"
  title: "show_if visible"
  width: 320
  height: 190
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/video_show, default: true}
        op: "=="
        right: true
- kind: Video
  id: components_test_video_yaml_hide_if
  source: "assets/test.mp4"
  title: "hide_if visible"
  width: 320
  height: 190
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/video_hide, default: false}
        op: "=="
        right: true
- kind: Video
  id: components_test_video_yaml_required_permissions
  source: "assets/test.mp4"
  title: "required_permissions gate"
  width: 320
  height: 190
  required_permissions: [components.media.visibility]</code></pre></div>
  </div>
</div>

The test page updates the observed store flags with the same action used by Python and YAML declarations:

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Video visibility controls example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-visibility-controls-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="video-visibility-controls-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="video-visibility-controls-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.Button(
        "components_test_video_show_off_btn",
        "Hide show_if",
        action="components.media_test_visibility_set",
        params={"component": "video", "flag": "show", "value": False},
        variant="default",
    )
)
builder.add(
    sdk.ui.Button(
        "components_test_video_hide_on_btn",
        "Hide hide_if",
        action="components.media_test_visibility_set",
        params={"component": "video", "flag": "hide", "value": True},
        variant="default",
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="video-visibility-controls-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: components_test_video_yaml_show_off_btn
  label: "Hide show_if"
  variant: default
  action: components.media_test_visibility_set
  params: {component: video, flag: show, value: false}
- kind: Button
  id: components_test_video_yaml_hide_on_btn
  label: "Hide hide_if"
  variant: default
  action: components.media_test_visibility_set
  params: {component: video, flag: hide, value: true}</code></pre></div>
  </div>
</div>

## Path Resolution

- Module asset paths such as `assets/test.mp4` and `assets/test2.mp4` resolve to media routes for the active module.
- `assets/protected/...` resolves to the same module media route but requires an authenticated user before the asset is served.
- `/media/...` is already a client-facing media path and is used as-is by the clients.
- `http://...` and `https://...` are external URLs. On web they are resolved through the media proxy when they are outside the core origin.

## Usage Guidance

- Use module asset paths for packaged video shipped with the module.
- Use store bindings when source, title, or poster must follow page or global client state.
- Use data model bindings when the player follows the surface data model.
- Use runtime property updates for source, title, and poster changes without a full rerender.
