# DashboardWidget

[<- Back to Layout Components](./index.md)

## Purpose

A draggable widget for the dashboard.

## Constructor

```python
DashboardWidget(
    id: str,
    size: str = 'square',
    title: str = '',
    children: Optional[List[Union[str, Component]]] = None
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `size` | `str` | `'square'` | `size` |
| `title` | `str` | `''` | `title` |
| `children` | `Optional[List[Union[str, Component]]]` | `None` | `children` |

## Full Python Example

```python
import sdk

component = sdk.ui.DashboardWidget(
    id='dashboardwidget_1',
    size='square',
    title='',
    children=None,
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
- kind: DashboardWidget
  id: dashboardwidget_1
  size: square
  title: ""
  children: null
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
