# Thread

[<- Back to Conversation Components](./index.md)

## Purpose

Conversation container that groups messages and chat controls.

For full chat applications, prefer explicit layout composition when you need a fixed toolbar, scrollable message window, and composer pinned outside the scroll area. `Thread` is a container primitive, not the source of reliable chat scrolling.

## Constructor

```python
Thread(
    id: str,
    children: Optional[List[Any]] = None,
    auto_scroll: bool = True
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `children` | `Optional[List[Any]]` | `None` | `children` |
| `auto_scroll` | `bool` | `True` | `auto_scroll` |

## Full Python Example

```python
import sdk

component = sdk.ui.Thread(
    id='thread_1',
    children=None,
    auto_scroll=True,
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
- kind: Thread
  id: thread_1
  children: null
  auto_scroll: true
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
