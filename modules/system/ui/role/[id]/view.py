from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.utils.actions.role.module import module_rows_for_role
from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.user.render import resolve_route_id, set_title_text


def _group_permissions(permission_names: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for permission in permission_names:
        value = str(permission or "").strip()
        if not value:
            continue
        module_name = value.split(".", 1)[0] if "." in value else "core"
        grouped.setdefault(module_name, []).append(value)
    for module_name in grouped:
        grouped[module_name] = sorted(set(grouped[module_name]))
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


async def render(params: dict, session: dict):
    role_id = resolve_route_id(params)
    breadcrumb_segments = None
    if role_id is None:
        page_builder = sdk.ui.Builder()
        page_builder.add(sdk.ui.Text("role_view_error", sdk.i18n.t("system.role.view.invalid_id")))
    else:
        role = sdk.models.roles.view(role_id)
        if role is None:
            page_builder = sdk.ui.Builder()
            page_builder.add(
                sdk.ui.Text(
                    "role_view_missing",
                    sdk.i18n.t("system.role.view.not_found"),
                )
            )
        else:
            page_builder = sdk.ui.load("utils/ui/yaml/roles/view")
            modules_builder = sdk.ui.load("utils/ui/yaml/roles/modules")
            merge_builders(page_builder, modules_builder)
            is_super_role = str(role.get("name") or "").strip().lower() == "super"
            all_permissions = [
                str(item.get("value") or "").strip()
                for item in (sdk.models.roles.form_model_extra("permissions_options") or [])
                if isinstance(item, dict) and str(item.get("value") or "").strip()
            ]
            role_permissions = {
                str(permission or "").strip()
                for permission in (role.get("permissions") or [])
                if str(permission or "").strip()
            }
            grouped_permissions = _group_permissions(all_permissions)

            title = page_builder.get_component("role_view_title")
            set_title_text(
                title,
                sdk.i18n.t(
                    "system.role.view.title",
                    context={"name": str(role.get("name") or "")},
                ),
            )
            breadcrumb_segments = [
                {
                    "label": sdk.i18n.t("system.role.list.title"),
                    "type": "nav",
                    "path": "/system/role/list",
                },
                {
                    "label": sdk.i18n.t(
                        "system.role.view.title",
                        context={"name": str(role.get("name") or "")},
                    ),
                    "current": True,
                },
            ]

            descriptions = page_builder.get_component("role_info_descriptions")
            if descriptions is not None:
                descriptions.set_property("data", role)

            update_btn = page_builder.get_component("role_open_update_btn")
            if update_btn is not None:
                update_btn.set_property(
                    "action",
                    {
                        "name": "open_drawer",
                        "context": {
                            "type": "nav",
                            "path": f"/system/role/{role_id}/update",
                        },
                    },
                )
                update_btn.set_property("enabled", not is_super_role)

            permissions_mount = page_builder.get_component("role_permissions_mount")
            module_section_ids: list[str] = []
            accordion_items: list[dict] = []
            accordion_children: list[str] = []
            for index, (module_name, permission_names) in enumerate(
                grouped_permissions.items()
            ):
                section_id = f"role_permissions_module_{index}"
                section_body_id = f"{section_id}_body"
                permission_item_ids: list[str] = []
                accordion_items.append(
                    {
                        "title": sdk.i18n.t(
                            "system.role.permissions.module_title",
                            context={"module": module_name},
                        ),
                        "content": "",
                        "open": index == 0,
                    }
                )
                for perm_index, permission_name in enumerate(permission_names):
                    toggle_id = f"{section_id}_toggle_{perm_index}"
                    row_id = f"{section_id}_row_{perm_index}"
                    card_id = f"{section_id}_card_{perm_index}"
                    toggle = sdk.ui.Toggle(
                        toggle_id,
                        permission_name,
                        checked=permission_name in role_permissions,
                        action="system.toggle_role_permission",
                        params={
                            "role_id": role_id,
                            "permission": permission_name,
                            "toggle_id": toggle_id,
                        },
                    )
                    toggle.set_property("enabled", not is_super_role)
                    page_builder.add(toggle)
                    row_children = [toggle_id]
                    if permission_name in role_permissions:
                        badge_id = f"{section_id}_badge_{perm_index}"
                        page_builder.add(
                            sdk.ui.Badge(
                                badge_id,
                                sdk.i18n.t("system.role.permissions.assigned_badge"),
                                variant="success",
                            )
                        )
                        row_children.append(badge_id)

                    row = sdk.ui.Row(row_id, row_children)
                    row.set_property("justify", "between")
                    row.set_property("align", "center")
                    page_builder.add(row)

                    card = sdk.ui.Card(card_id, [row_id], variant="outlined")
                    permission_item_ids.append(card_id)
                    page_builder.add(card)

                body = sdk.ui.Column(section_body_id, permission_item_ids)
                body.set_property("spacing", 8)
                page_builder.add(body)
                accordion_children.append(section_body_id)
            if accordion_items:
                accordion_id = "role_permissions_accordion"
                accordion = sdk.ui.Accordion(
                    accordion_id,
                    items=accordion_items,
                    multiple=False,
                    collapsible=True,
                )
                accordion.children.extend(accordion_children)
                page_builder.add(accordion)
                module_section_ids.append(accordion_id)
            if not module_section_ids:
                empty_id = "role_permissions_empty"
                page_builder.add(
                    sdk.ui.Text(empty_id, sdk.i18n.t("system.role.permissions.empty"))
                )
                module_section_ids.append(empty_id)
            if permissions_mount is not None:
                permissions_mount.set_children(
                    [
                        "role_permissions_title",
                        "role_permissions_subtitle",
                        *module_section_ids,
                    ]
                )

            role_module_rows = module_rows_for_role(role_id, sdk)
            modules_table = page_builder.get_component("role_modules_table")
            if modules_table is not None:
                modules_table.set_property("rows", role_module_rows)
                modules_table.set_property("total_rows", len(role_module_rows))
                if is_super_role:
                    modules_table.set_property("row_actions", [])

    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    if breadcrumb_segments is not None:
        builder.set_store(
            "/role_view/breadcrumb_segments",
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
