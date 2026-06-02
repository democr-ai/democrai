from __future__ import annotations

from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


def _with_drawer_options(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved = list(messages)
    for message in reversed(resolved):
        begin = message.get("beginRendering")
        if isinstance(begin, dict) and str(begin.get("surfaceId") or "") == "drawer":
            begin["options"] = {"position": "right", "dim": 980}
            break
    return resolved


@action("open_attachment_preview")
@permission_required(["chat.view"])
async def open_attachment_preview(ctx: dict[str, Any], session: dict, module_sdk):
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
    preview.set_property("style", "height: 100%; min-height: 0;")

    root = module_sdk.ui.Column("chat_attachment_preview_root", ["chat_attachment_preview"])
    root.set_property("stretch", True)
    root.set_property("style", "height: 100%; min-height: 0;")

    builder = module_sdk.ui.Builder()
    builder.add(preview)
    builder.add(root)

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            _with_drawer_options(
                module_sdk.effects.build_aux_surface_messages(builder, "drawer")
            )
        )
    )
