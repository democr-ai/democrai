# ThreadList

[<- Back to Conversation Components](./index.md)

## Purpose

List of conversation threads with optional active-thread tracking.

## Constructor

```python
ThreadList(
    id: str,
    threads: Optional[List[Dict[str, Any]]] = None,
    active_thread_id: str = '',
    action: Optional[str | ActionSpec] = None,
    params: Optional[dict] = None
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `threads` | `Optional[List[Dict[str, Any]]]` | `None` | `threads` |
| `active_thread_id` | `str` | `''` | `active_thread_id` |
| `action` | `Optional[str | ActionSpec]` | `None` | `action` |

## Action Confirmation

Use `action.confirm` to ask for confirmation before dispatching the selected thread action. On desktop, cancelling keeps the previous confirmed active thread selected.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ThreadList confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="threadlist-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="threadlist-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="threadlist-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>component = sdk.ui.ThreadList(
    "threadlist_confirm",
    threads=[
        {"id": "thread_alpha", "title": "Alpha thread", "preview": "First thread"},
        {"id": "thread_beta", "title": "Beta thread", "preview": "Second thread"},
    ],
    active_thread_id="thread_alpha",
    action={
        "name": "components.threadlist_confirm_action",
        "context": {"source": "python_threadlist"},
        "confirm": {
            "text": sdk.i18n.t("components.threadlist.confirm.prompt"),
            "confirm_text": sdk.i18n.t("components.threadlist.confirm.accept"),
            "cancel_text": sdk.i18n.t("components.threadlist.confirm.cancel"),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="threadlist-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ThreadList
  id: threadlist_confirm
  threads:
    - id: thread_alpha
      title: Alpha thread
      preview: First thread
    - id: thread_beta
      title: Beta thread
      preview: Second thread
  active_thread_id: thread_alpha
  action:
    name: components.threadlist_confirm_action
    context:
      source: yaml_threadlist
    confirm:
      text: "@t/components.threadlist.confirm.prompt"
      confirm_text: "@t/components.threadlist.confirm.accept"
      cancel_text: "@t/components.threadlist.confirm.cancel"</code></pre></div>
  </div>
</div>
| `params` | `Optional[dict]` | `None` | `params` |

## Full Python Example

```python
import sdk

component = sdk.ui.ThreadList(
    id='threadlist_1',
    threads=None,
    active_thread_id='',
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
- kind: ThreadList
  id: threadlist_1
  threads: null
  active_thread_id: ""
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
