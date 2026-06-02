# AI Attachment Preview

[<- Back to AI Chat](./index.md)

Use `AttachmentPreview` only when a module explicitly chooses to render an attachment preview.

`MessageList` does not open this component automatically. Attachment clicks are application actions; the module receives the attachment payload and owns the next step.

## Parameters

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `name` | yes | yes | practical no | File name |
| `mime` | yes | yes | practical no | Drives preview branch |
| `path` | yes | yes | practical no | File source |
| `source_path` | yes | yes | practical no | File source |
| `file_id` | no direct | yes | practical no | Desktop consumes it directly |
| `url` | yes | yes | practical no | Preferred cross-client source |
| `height` | yes | yes | practical no | Preview height |
| `style` | yes | yes | yes | Wrapper styling |

Cross-renderer rule:

- Always provide `url` or `source_path` for previewable files.
- Do not rely on `file_id` alone if the flow must also work on web.

## Example

```python
preview = sdk.ui.AttachmentPreview(
    "attachment_preview",
    name="candidate-brief.pdf",
    mime="application/pdf",
    source_path="/abs/path/candidate-brief.pdf",
    url="https://example.invalid/candidate-brief.pdf",
    height=420,
)
```

## Attachment Click Flow

Recommended pattern:

1. `MessageList` exposes `on_attachment_click`.
2. Clicking an image or PDF emits an action with attachment context.
3. The action decides what to do with that payload.
4. If the module needs a preview, it explicitly renders `AttachmentPreview` or another dedicated content/document viewer.

Recommended action payload fields:

- `message_id`
- `message_role`
- `name`
- `mime`
- `path`
- `source_path`
- `file_id`
- `url`
