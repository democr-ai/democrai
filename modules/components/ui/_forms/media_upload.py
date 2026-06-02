from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk
from ..demo_helpers import page_header, showcase_card, mount_preview
from ..layout import shared_layout


@permission_required(["components.documentation.view"])
async def render(params: dict, session: dict) -> sdk.ui.Builder:
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    header_id = page_header(
        builder,
        "media_upload_header",
        "Form Components",
        "Media Upload",
        "Sandbox page for deferred uploads: explicit upload on button action and automatic upload during form submit.",
    )

    builder.add(
        sdk.ui.Attachment(
            "media_upload_input",
            label="Select a file to upload",
            multiple=False,
        )
    )
    builder.add(
        sdk.ui.Button(
            "media_upload_submit",
            "Upload Then Print Context",
            action="components.media_upload_debug",
            params={"upload_input_id": "media_upload_input"},
            variant="primary",
        )
    )

    showcase_card(
        builder,
        "media_upload_button_card",
        "Explicit Upload From Button",
        "This case keeps the attachment local until the button action runs. The button uses `upload_input_id` to materialize the upload before dispatching the action.",
        ["media_upload_input", "media_upload_submit"],
    )

    form_demo = sdk.ui.Form(
        id="media_upload_form",
        submit_label="Submit Form Upload",
        action={"name": "components.media_upload_debug"},
        model=[
            {
                "name": "title",
                "label": "Document Title",
                "type": "text",
                "placeholder": "Quarterly report",
                "validations": [
                    {"rule": "required", "message": "Title is required"},
                ],
            },
            {
                "name": "attachment",
                "label": "Form Attachment",
                "type": "attachment",
                "multiple": False,
                "validations": [
                    {"rule": "required", "message": "Select one file"},
                ],
            },
        ],
    )
    builder.add(form_demo)

    showcase_card(
        builder,
        "media_upload_form_card",
        "Upload Inside Form Submit",
        "This case keeps the file local until the form submit pipeline uploads the attachment and then dispatches the final action payload.",
        ["media_upload_form"],
    )

    doc = """
### Media Upload

This page now demonstrates the two deferred-upload paths supported by the clients.

#### 1. Explicit upload from a separate button

- the `Attachment` keeps a local/transient value
- the button sets `params={"upload_input_id": "media_upload_input"}`
- the client uploads before dispatching the action

#### 2. Upload during `Form` submit

- the `Attachment` inside the form also keeps a local/transient value
- the form submit pipeline uploads attachment fields before dispatching the action

Both demos still use the same debug action, so you can inspect the final server-side `ctx`.
"""
    builder.add(sdk.ui.Markdown("media_upload_doc", doc))
    builder.add(sdk.ui.Column("media_upload_footer", ["media_upload_doc"]))
    builder.get_component("media_upload_footer").set_property("margin_top", 40)

    root = sdk.ui.Column(
        "media_upload_root",
        [
            "media_upload_header",
            "media_upload_button_card",
            "media_upload_form_card",
            "media_upload_footer",
        ],
    )
    root.set_property("spacing", 24)
    builder.add(root)

    mount_preview(builder, preview_id, "media_upload_root")
    return builder
