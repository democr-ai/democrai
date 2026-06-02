# ScrollToBottomButton

[<- Back to Conversation Components](./index.md)

## Purpose

Utility button that returns the conversation viewport to the latest content.

## Constructor

```python
ScrollToBottomButton(
    id: str,
    label: str = 'Jump to latest',
    action: Optional[str | ActionSpec] = None,
    params: Optional[dict] = None
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `label` | `str` | `'Jump to latest'` | `label` |
| `action` | `Optional[str | ActionSpec]` | `None` | `action` |

## Action Confirmation

Use `action.confirm` to ask for confirmation before the scroll action dispatches. Confirmation text should use translation keys.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ScrollToBottomButton confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scroll-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scroll-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="scroll-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>component = sdk.ui.ScrollToBottomButton(
    "scroll_confirm",
    label=sdk.i18n.t("components.scroll.confirm.python_label"),
    action={
        "name": "components.scroll_confirm_action",
        "context": {"source": "python_scroll"},
        "confirm": {
            "text": sdk.i18n.t("components.scroll.confirm.prompt"),
            "confirm_text": sdk.i18n.t("components.scroll.confirm.accept"),
            "cancel_text": sdk.i18n.t("components.scroll.confirm.cancel"),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="scroll-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ScrollToBottomButton
  id: scroll_confirm
  label: "@t/components.scroll.confirm.yaml_label"
  action:
    name: components.scroll_confirm_action
    context:
      source: yaml_scroll
    confirm:
      text: "@t/components.scroll.confirm.prompt"
      confirm_text: "@t/components.scroll.confirm.accept"
      cancel_text: "@t/components.scroll.confirm.cancel"</code></pre></div>
  </div>
</div>
| `params` | `Optional[dict]` | `None` | `params` |

## Full Python Example

```python
import sdk

component = sdk.ui.ScrollToBottomButton(
    id='scrolltobottombutton_1',
    label='Jump to latest',
    action=None,
    params=None,
)

component.set_required_permissions(['system.user.view'])
component.set_show_if({
    'mode': 'AND',
    'conditions': [
        {
            'left': {'type': 'store', 'scope': 'page', 'path': '/can_view'},
            'op': '==',
            'right': True,
        }
    ],
})
component.allow('visible.set', 'enabled.set')
```

## Full YAML Example

```yaml
- kind: ScrollToBottomButton
  id: scrolltobottombutton_1
  label: Jump to latest
  action: null
  params: null
  required_permissions:
    - system.user.view
  show_if:
    mode: AND
    conditions:
      - left:
          type: store
          scope: page
          path: /can_view
        op: "=="
        right: true
  capabilities:
    - visible.set
    - enabled.set
```
