from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.actions.user.module import module_rows_for_user
from modules.system.ui.layout import shared_layout
from democrai.sdk.ui import merge_builders
from modules.system.utils.ui.user.render import resolve_route_id, set_title_text



async def render(params: dict, session: dict):

    user_id = resolve_route_id(params)
    breadcrumb_segments = None
    if user_id is None:
        page_builder = sdk.ui.Builder()
        page_builder.add(sdk.ui.Text("user_view_error", sdk.i18n.t("system.user.view.invalid_id")))
    else:
        user = sdk.models.users.view(user_id)
        if user is None:
            page_builder = sdk.ui.Builder()
            page_builder.add(
                sdk.ui.Text(
                    "user_view_missing",
                    sdk.i18n.t("system.user.view.not_found"),
                )
            )
        else:
            page_builder = sdk.ui.load("utils/ui/yaml/user/view")
            modules_builder = sdk.ui.load("utils/ui/yaml/user/modules")
            merge_builders(page_builder, modules_builder)

            title = page_builder.get_component("user_view_title")
            set_title_text(
                title,
                sdk.i18n.t(
                    "system.user.view.title",
                    context={"username": str(user.get("username") or "")},
                ),
            )
            breadcrumb_segments = [
                {
                    "label": sdk.i18n.t("system.user.list.title"),
                    "type": "nav",
                    "path": "/system/user/list",
                },
                {
                    "label": sdk.i18n.t(
                        "system.user.view.title",
                        context={"username": str(user.get("username") or "")},
                    ),
                    "current": True,
                },
            ]

            descriptions = page_builder.get_component("user_info_descriptions")
            if descriptions is not None:
                descriptions.set_property("data", user)

            update_btn = page_builder.get_component("user_open_update_btn")
            if update_btn is not None:
                update_btn.set_property(
                    "action",
                    {
                        "name": "open_drawer",
                        "context": {
                            "type": "nav",
                            "path": f"/system/user/{user_id}/update",
                        },
                    },
                )

            change_pwd_btn = page_builder.get_component("user_open_password_btn")
            if change_pwd_btn is not None:
                change_pwd_btn.set_property(
                    "action",
                    {
                        "name": "open_drawer",
                        "context": {
                            "type": "nav",
                            "path": f"/system/user/{user_id}/change_password",
                        },
                    },
                )

            module_rows = module_rows_for_user(user_id, sdk)
            modules_table = page_builder.get_component("user_modules_table")
            if modules_table is not None:
                modules_table.set_property("rows", module_rows)
                modules_table.set_property("total_rows", len(module_rows))

    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    if breadcrumb_segments is not None:
        builder.set_store(
            "/user_view/breadcrumb_segments",
            breadcrumb_segments,
            scope="page",
        )

    merge_builders(builder, page_builder)

    root_ids = [component.id for component in page_builder.get_roots() if component.id]
    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(root_ids)
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
