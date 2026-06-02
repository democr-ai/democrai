# Flow

[<- Back to Layout Components](./index.md)

## Purpose

A layout component that wraps its children horizontally.

## Constructor

```python
Flow(
    id: str,
    children: Optional[List[Union[str, Component]]] = None,
    spacing: int = 10
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `children` | `Optional[List[Union[str, Component]]]` | `None` | `children` |
| `spacing` | `int` | `10` | `spacing` |

## Full Python Example

```python
import sdk

component = sdk.ui.Flow(
    id='flow_1',
    children=None,
    spacing=10,
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
- kind: Flow
  id: flow_1
  children: null
  spacing: 10
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
