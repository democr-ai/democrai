# AttachmentPreview

[<- Back to Conversation Components](./index.md)

## Purpose

Inline attachment preview component for document surfaces.

`MessageList` does not open `AttachmentPreview` automatically. Attachment clicks emit an action payload; the application owns the next step.

## Constructor

```python
AttachmentPreview(
    id: str
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |

## Derived / Implicit Keys Set by SDK

The constructor also writes these fixed or computed keys in the serialized payload:

- `file_id`
- `height`
- `mime`
- `name`
- `path`
- `source_path`
- `url`

## Full Python Example

```python
import sdk

component = sdk.ui.AttachmentPreview(
    id='attachmentpreview_1',
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
- kind: AttachmentPreview
  id: attachmentpreview_1
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
