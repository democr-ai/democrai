from democrai.sdk.decorators import ui_template
from democrai.sdk.ui import Builder, ui
from democrai.core.platform.ui.tags import APP_LANGUAGE_TAG

@ui_template("empty")
def template(*args, **kwargs):
    """
    Empty template that just renders the content area.
    """
    builder = Builder()

    # --- Router Dispatch ---
    module_root_id = "content_area_container"

    # --- Root Shell ---
    # Just a column containing the content
    root = ui.Column("root", ["empty_language_bar", module_root_id])
    root.set_property("stretch", True)
    root.set_property("align", "fill")
    builder.add(root)

    language_tag = ui.ClientTag("empty_language_selector", APP_LANGUAGE_TAG)
    builder.add(language_tag)

    language_bar = ui.Row("empty_language_bar", ["empty_language_selector"])
    language_bar.set_property("align", "right")
    language_bar.set_property("padding", [12, 12, 0, 12])
    builder.add(language_bar)

    # --- Central Subsurface Host ---
    content_host = ui.SurfaceHost("content_area_host", surface_id="main_content")
    content_host.set_property("tag", "@main_content")
    content_host.set_property("stretch", True)
    builder.add(content_host)

    # Wrap it in a content area if needed, or just add it to root
    module_root = ui.ContentArea(module_root_id, ["content_area_host"])
    module_root.set_property("stretch", True)
    builder.add(module_root)

    # content = json.dumps(
    # {
    # "surfaceId": "root",
    # "components": [c.to_dict() for c in builder._components],
    # }
    # )

    dimensions = "window"
    return [c.to_dict() for c in builder._components], dimensions
