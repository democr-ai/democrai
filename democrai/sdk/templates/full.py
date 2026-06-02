from democrai.sdk.decorators import ui_template
from democrai.sdk.ui import Builder, ui
from democrai.core.platform.ui.tags import (
    APP_BOTTOM_MAIN_LIST_TAG,
    APP_MAIN_LIST_TAG,
    APP_NOTIFICATIONS_TAG,
)


@ui_template("full")
def template(*args, **kwargs):
    """Build the default full-shell application template with sidebar and content host."""
    builder = Builder()

    # --- Shell Structure ---
    root = ui.Column("root", ["main_layout"])
    root.set_property("stretch", True)
    builder.add(root)

    # --- Sidebar ---
    builder.add(ui.Image("logo_img", "Democr.ai Logo", url="assets/logo.svg"))
    logo_slot = ui.Column("logo_slot", ["logo_img"])
    logo_slot.set_property("align", "center")
    builder.add(logo_slot)

    # --- Dynamic Sidebar Tags ---
    # position="bottom" tells mobile clients to render this as a bottom tab bar
    top_nav = ui.ClientTag("top_nav", APP_MAIN_LIST_TAG)
    top_nav.set_property("position", "bottom")
    builder.add(top_nav)

    # Spacer to push bottom items down
    spacer = ui.FlexContainer("nav_spacer")
    builder.add(spacer)

    # Notifications bell
    notifications = ui.ClientTag("notifications_bell", APP_NOTIFICATIONS_TAG)
    builder.add(notifications)

    # Bottom Navigation
    bottom_nav = ui.ClientTag("bottom_nav", APP_BOTTOM_MAIN_LIST_TAG)
    builder.add(bottom_nav)

    main_sidebar = ui.Sidebar(
        "main_sidebar",
        ["logo_slot", "top_nav", "nav_spacer", "notifications_bell", "bottom_nav"],
    )
    main_sidebar.set_property("padding", [16, 0, 16, 0])
    main_sidebar.set_property("align", "center")
    builder.add(main_sidebar)

    # --- Central Content ---
    central_content = ui.FlexContainer("central_content", ["content_area"])
    builder.add(central_content)

    # --- Main Layout ---
    main_layout = ui.Row("main_layout", ["main_sidebar", "central_content"])
    main_layout.set_property("stretch", True)
    main_layout.set_property("align", "fill")
    builder.add(main_layout)

    # --- Central Subsurface Host ---
    content_host = ui.SurfaceHost("content_area_host", surface_id="main_content")
    content_host.set_property("tag", "@main_content")
    # content_host.set_property("stretch", True)
    builder.add(content_host)

    # Required wrapper for RenderService._finalize_layout
    content_container = ui.FlexContainer(
        "content_area_container", ["content_area_host"]
    )
    builder.add(content_container)

    # Finalize Content Wrapper
    content_area = ui.ContentArea("content_area", ["content_area_container"])
    # content_area.set_property("stretch", True)
    content_area.set_property("align", "fill")
    builder.add(content_area)

    # content = json.dumps(
    # {
    # "surfaceId": "root",
    # "components": [c.to_dict() for c in builder._components],
    # }
    # )
    dimensions = "full"
    return [c.to_dict() for c in builder._components], dimensions
