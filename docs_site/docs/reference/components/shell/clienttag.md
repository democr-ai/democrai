# ClientTag

[<- Back to Shell Components](./index.md)

## Purpose

Placeholder resolved by the client into concrete UI components.

## Constructor

```python
ClientTag(
    id: str,
    tag: Any
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `tag` | `Any` | `required` | `tag` |

## Full Python Example

```python
import sdk

component = sdk.ui.ClientTag(
    id='clienttag_1',
    tag='tag value',
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
- kind: ClientTag
  id: clienttag_1
  tag: tag value
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
