# Header + Content

[<- Back to Ready Layouts](./index.md)

This ready layout fills the available window height with a top header and a scrollable content area below it.

Use this structure when the page has a persistent top bar and the body should absorb the remaining height. The root owns the viewport height; the content body stretches inside it and keeps `min-height: 0` so the inner `ScrollArea` can receive a bounded height.

![Header + Content preview](../../../../assets/screen/layout/head_cont.png)

## Structure

- The root `Column` owns the page background and viewport height.
- The `Header` keeps natural height and does not receive `100vh`.
- The body `Column` uses `stretch: true` and `min-height: 0`.
- `ContentArea` stretches inside the body and contains the scrollable page content.
- `ScrollArea` disables horizontal scrolling with `scroll_x: false`.

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Header + Content layout example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="header-content-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="header-content-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="header-content-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>prefix = "components_full_test_header_content"

header = sdk.ui.Header(f"{prefix}_header", left=[], center=[], right=[])
header.set_property("style", "min-height: 64px;")
builder.add(header)

content_stack = sdk.ui.Column(f"{prefix}_content_stack", [])
builder.add(content_stack)

content_scroll = sdk.ui.ScrollArea(f"{prefix}_content_scroll", [content_stack.id])
content_scroll.set_property("scroll_x", False)
content_scroll.set_property("transparent", True)
content_scroll.set_property("stretch", True)
builder.add(content_scroll)

content = sdk.ui.ContentArea(f"{prefix}_content", [content_scroll.id])
content.set_property("stretch", True)
builder.add(content)

body = sdk.ui.Column(f"{prefix}_body", [content.id])
body.set_property("align", "fill")
body.set_property("stretch", True)
body.set_property("style", "min-height: 0;")
builder.add(body)

shell = sdk.ui.Column(f"{prefix}_shell", [header.id, body.id])
shell.set_property("align", "fill")
shell.set_property("spacing", 12)
shell.set_property("stretch", True)
shell.set_property("style", "height: 100%; min-height: 0;")
builder.add(shell)

root = sdk.ui.Column(f"{prefix}_root", [shell.id])
root.set_property("align", "fill")
root.set_property("style", "height: 100vh; min-height: 100vh;")
builder.add(root)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="header-content-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Column
  id: components_full_test_header_content_yaml_root
  align: fill
  style: "height: 100vh; min-height: 100vh;"
  children:
    - kind: Column
      id: components_full_test_header_content_yaml_shell
      align: fill
      spacing: 12
      stretch: true
      style: "height: 100%; min-height: 0;"
      children:
        - kind: Header
          id: components_full_test_header_content_yaml_header
          style: "min-height: 64px;"
          left: []
          center: []
          right: []
        - kind: Column
          id: components_full_test_header_content_yaml_body
          align: fill
          stretch: true
          style: "min-height: 0;"
          children:
            - kind: ContentArea
              id: components_full_test_header_content_yaml_content
              stretch: true
              children:
                - kind: ScrollArea
                  id: components_full_test_header_content_yaml_content_scroll
                  scroll_x: false
                  transparent: true
                  stretch: true
                  children:
                    - kind: Column
                      id: components_full_test_header_content_yaml_content_stack
                      children: []</code></pre></div>
  </div>
</div>

## Notes

- Use `100vh` on the root only.
- Do not put `100vh` on the content body below the header.
- Keep the body and shell at `min-height: 0` so the scroll area can shrink and scroll instead of forcing page overflow.
