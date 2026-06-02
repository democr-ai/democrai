from democrai.sdk.auth import permission_required
from ..demo_helpers import mount_preview, page_header
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(params: dict, session: dict) -> sdk.ui.Builder:
    builder = sdk.ui.Builder()
    root_id, preview_id = await shared_layout(builder)

    header_id = page_header(
        builder,
        "icons_header",
        "Icons",
        "Remix Icons Gallery",
        "A large collection of icons from the Remix Icons library. Click to copy name.",
    )

    # On desktop, we split into two tags to avoid focus loss during reactive filtering.
    # icon_controls is static and holds the TextField + Search button.
    # icon_gallery is dynamic and holds the grid + pagination info.
    builder.add(sdk.ui.ClientTag("icon_controls_host", tag="icon_controls"))
    builder.add(sdk.ui.ClientTag("icon_gallery_host", tag="icon_gallery"))

    gallery_container = sdk.ui.Column(
        "gallery_container", ["icon_controls_host", "icon_gallery_host"]
    )
    gallery_container.set_property("flex", 1)
    gallery_container.set_property("min_height", 600)
    builder.add(gallery_container)

    root = sdk.ui.Column("icons_root", [header_id, "gallery_container"])
    root.set_property("spacing", 20)
    root.set_property("flex", 1)
    root.set_property("style", "height: 100%;")
    builder.add(root)

    mount_preview(builder, preview_id, "icons_root")
    return builder
