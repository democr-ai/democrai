from democrai.sdk.client import active_sdk as sdk


def page_header(builder, header_id: str, eyebrow: str, title: str, description: str):
    builder.add(sdk.ui.Title(f"{header_id}_eyebrow", eyebrow, 4))
    builder.add(sdk.ui.Title(f"{header_id}_title", title, 1))
    builder.add(sdk.ui.Text(f"{header_id}_desc", description))

    container = sdk.ui.Column(
        header_id,
        [f"{header_id}_eyebrow", f"{header_id}_title", f"{header_id}_desc"],
    )
    container.set_property("style", "margin-bottom: 12px")
    builder.add(container)
    builder.get_component(header_id).set_property("spacing", 8)
    return header_id


def showcase_card(
    builder,
    card_id: str,
    title: str,
    description: str,
    children: list[str],
):
    builder.add(sdk.ui.Title(f"{card_id}_title", title, 3))
    builder.add(sdk.ui.Text(f"{card_id}_desc", description))
    builder.get_component(f"{card_id}_desc").set_property(
        "style", "font-size: 13px;"
    )

    content_id = f"{card_id}_content"
    builder.add(sdk.ui.Column(content_id, children))
    builder.get_component(content_id).set_property("spacing", 14)

    builder.add(
        sdk.ui.Card(
            card_id,
            [f"{card_id}_title", f"{card_id}_desc", content_id],
            variant="outlined",
        )
    )
    builder.get_component(card_id).set_property("padding", [20, 20, 20, 20])
    builder.get_component(card_id).set_property("spacing", 14)
    builder.get_component(card_id).set_property("style", "margin-bottom: 12px;")
    return card_id


def two_col_row(builder, row_id: str, left: str, right: str):
    _left = sdk.ui.Column(row_id + "_col1", [left])
    _right = sdk.ui.Column(row_id + "_col2", [right])
    builder.add(sdk.ui.Row(row_id, [_left, _right]))
    builder.get_component(row_id).set_property("spacing", 18)
    return row_id


def code_block(builder, block_id: str, code: str):
    md = sdk.ui.Markdown(block_id, f"```python\n{code.strip()}\n```")
    md.set_property("style", "margin-top: 12px; margin-bottom: 12px;")
    builder.add(md)
    return block_id


def mount_preview(builder, preview_id: str, root_id: str):
    preview = builder.get_component(preview_id)
    preview.set_children([root_id])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
