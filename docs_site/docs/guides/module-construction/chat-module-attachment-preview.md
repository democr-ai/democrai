# Chat Module Attachment Preview

This step adds file preview behavior.

Preview is a UI concern. Document understanding stays in tools such as
`chat.list-attachments`, `chat.search-documents`, `chat.read-document`, and
`chat.extract-full-summary`.

## Attachment Click Contract

`MessageList` dispatches `chat.open_attachment_preview` when the user clicks an
attachment:

```yaml
on_attachment_click:
  name: chat.open_attachment_preview
  context:
    source: chat_message_list
```

The action receives the clicked attachment payload. The current chat rows use:

```python
{
    "name": "document.pdf",
    "mime_type": "application/pdf",
    "storage_path": "media/chat/document.pdf",
    "file_id": "media-file-id",
}
```

`storage_path` is a stored media reference, not a client URL.

## Preview Action

`modules/chat/actions/attachments.py` resolves the stored path through the SDK
and renders an `AttachmentPreview` into the drawer:

```python
@action("open_attachment_preview")
@permission_required(["chat.view"])
async def open_attachment_preview(ctx: dict, session: dict, module_sdk):
    storage_path = ctx["storage_path"]
    public_url = module_sdk.media.get_public_url(storage_path) if storage_path else None

    preview = module_sdk.ui.AttachmentPreview(
        "chat_attachment_preview",
        name=ctx["name"],
        mime_type=ctx["mime_type"],
        storage_path=storage_path,
        file_id=ctx["file_id"],
        url=str(public_url or ""),
        height=760,
    )
    ...
```

The action then builds a small `Builder`, calls
`module_sdk.effects.build_aux_surface_messages(builder, "drawer")`, and returns
those messages through `module_sdk.effects.respond(...)`.

The current action also adjusts drawer options for the preview surface:

```python
begin["options"] = {"position": "right", "dim": 980}
```

That keeps large previews usable without changing the page layout.

## Media Boundary

Do this:

```python
public_url = module_sdk.media.get_public_url(storage_path)
```

Do not construct runtime media URLs manually. Web, desktop, local storage, and
distributed storage can require different URL/materialization behavior.

## Preview Is Not Retrieval

Preview lets the user inspect a file. The model still uses tool contracts:

- `chat.list-attachments` for attachment and extraction status;
- `chat.search-documents` for targeted content search;
- `chat.read-document` for bounded document blocks;
- `chat.extract-full-summary` for cached large-document maps.
