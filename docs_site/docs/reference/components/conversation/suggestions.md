# Suggestions

[<- Back to Conversation Components](./index.md)

## Purpose

Suggested prompts or actions for a conversation surface.

## Constructor

```python
Suggestions(
    id: str,
    suggestions: Optional[List[Dict[str, Any]]] = None,
    action: Optional[str | ActionSpec] = None,
    params: Optional[dict] = None
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `suggestions` | `Optional[List[Dict[str, Any]]]` | `None` | `suggestions` |
| `action` | `Optional[str | ActionSpec]` | `None` | `action` |

## Action Confirmation

Use `action.confirm` to ask for confirmation before dispatching a suggestion action. Confirmation text should use translation keys.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Suggestions confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="suggestions-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="suggestions-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="suggestions-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>component = sdk.ui.Suggestions(
    "suggestions_confirm",
    suggestions=[
        {"label": sdk.i18n.t("components.suggestions.confirm.item_one"), "prompt": "First prompt"},
        {"label": sdk.i18n.t("components.suggestions.confirm.item_two"), "prompt": "Second prompt"},
    ],
    action={
        "name": "components.suggestions_confirm_action",
        "context": {"source": "python_suggestions"},
        "confirm": {
            "text": sdk.i18n.t("components.suggestions.confirm.prompt"),
            "confirm_text": sdk.i18n.t("components.suggestions.confirm.accept"),
            "cancel_text": sdk.i18n.t("components.suggestions.confirm.cancel"),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="suggestions-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Suggestions
  id: suggestions_confirm
  suggestions:
    - label: "@t/components.suggestions.confirm.item_one"
      prompt: First YAML prompt
    - label: "@t/components.suggestions.confirm.item_two"
      prompt: Second YAML prompt
  action:
    name: components.suggestions_confirm_action
    context:
      source: yaml_suggestions
    confirm:
      text: "@t/components.suggestions.confirm.prompt"
      confirm_text: "@t/components.suggestions.confirm.accept"
      cancel_text: "@t/components.suggestions.confirm.cancel"</code></pre></div>
  </div>
</div>
| `params` | `Optional[dict]` | `None` | `params` |

## Full Python Example

```python
import sdk

component = sdk.ui.Suggestions(
    id='suggestions_1',
    suggestions=None,
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
- kind: Suggestions
  id: suggestions_1
  suggestions: null
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
