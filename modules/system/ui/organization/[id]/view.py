from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.utils.actions.organization import (
    module_rows_for_organization,
    organization_agent_rows,
    organization_mcp_rows,
    organization_tool_rows,
    organization_user_rows,
)
from modules.system.utils.actions.engine.quotas import (
    quota_limit_table_model,
)
from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.user.render import resolve_route_id, set_title_text


async def render(params: dict, session: dict):
    organization_id = resolve_route_id(params)
    breadcrumb_segments = None
    if organization_id is None:
        page_builder = sdk.ui.Builder()
        page_builder.add(
            sdk.ui.Text(
                "organization_view_error",
                sdk.i18n.t("system.organization.view.invalid_id"),
            )
        )
    else:
        organization = sdk.models.organizations.view(organization_id)
        if organization is None:
            page_builder = sdk.ui.Builder()
            page_builder.add(
                sdk.ui.Text(
                    "organization_view_missing",
                    sdk.i18n.t("system.organization.view.not_found"),
                )
            )
        else:
            page_builder = sdk.ui.load("utils/ui/yaml/organization/view")
            users_builder = sdk.ui.load("utils/ui/yaml/organization/users")
            modules_builder = sdk.ui.load("utils/ui/yaml/organization/modules")
            agents_builder = sdk.ui.load("utils/ui/yaml/organization/agents")
            tools_builder = sdk.ui.load("utils/ui/yaml/organization/tools")
            mcp_builder = sdk.ui.load("utils/ui/yaml/organization/mcp")
            quotas_builder = sdk.ui.load("utils/ui/yaml/engine/quota_limits")
            merge_builders(page_builder, users_builder)
            merge_builders(page_builder, modules_builder)
            merge_builders(page_builder, agents_builder)
            merge_builders(page_builder, tools_builder)
            merge_builders(page_builder, mcp_builder)
            merge_builders(page_builder, quotas_builder)

            title = page_builder.get_component("organization_view_title")
            set_title_text(
                title,
                sdk.i18n.t(
                    "system.organization.view.title",
                    context={"name": str(organization.get("name") or "")},
                ),
            )
            breadcrumb_segments = [
                {
                    "label": sdk.i18n.t("system.organization.list.title"),
                    "type": "nav",
                    "path": "/system/organization/list",
                },
                {
                    "label": sdk.i18n.t(
                        "system.organization.view.title",
                        context={"name": str(organization.get("name") or "")},
                    ),
                    "current": True,
                },
            ]

            descriptions = page_builder.get_component("organization_info_descriptions")
            if descriptions is not None:
                descriptions.set_property("data", organization)

            update_btn = page_builder.get_component("organization_open_update_btn")
            if update_btn is not None:
                update_btn.set_property(
                    "action",
                    {
                        "name": "open_drawer",
                        "context": {
                            "type": "nav",
                            "path": f"/system/organization/{organization_id}/update",
                        },
                    },
                )

            new_user_btn = page_builder.get_component("organization_user_new_btn")
            if new_user_btn is not None:
                new_user_btn.set_property(
                    "action",
                    {
                        "name": "open_drawer",
                        "context": {
                            "type": "nav",
                            "path": f"/system/organization/{organization_id}/user/create",
                        },
                    },
                )

            user_rows, total_users = organization_user_rows(organization_id, sdk)
            users_table = page_builder.get_component("organization_users_table")
            if users_table is not None:
                users_table.set_property("model", list(sdk.models.users.table_model() or []))
                users_table.set_property("rows", user_rows)
                users_table.set_property("total_rows", total_users)

            module_rows = module_rows_for_organization(organization_id, sdk)
            modules_table = page_builder.get_component("organization_modules_table")
            if modules_table is not None:
                modules_table.set_property("rows", module_rows)
                modules_table.set_property("total_rows", len(module_rows))

            agent_rows = organization_agent_rows(organization_id, sdk)
            agents_table = page_builder.get_component("organization_agents_table")
            if agents_table is not None:
                agents_table.set_property("rows", agent_rows)
                agents_table.set_property("total_rows", len(agent_rows))

            tool_rows = organization_tool_rows(organization_id, sdk)
            tools_table = page_builder.get_component("organization_tools_table")
            if tools_table is not None:
                tools_table.set_property("rows", tool_rows)
                tools_table.set_property("total_rows", len(tool_rows))

            mcp_rows = organization_mcp_rows(organization_id, sdk)
            mcp_table = page_builder.get_component("organization_mcp_table")
            if mcp_table is not None:
                mcp_table.set_property("rows", mcp_rows)
                mcp_table.set_property("total_rows", len(mcp_rows))

            page_builder.set_store(
                "/engine_quota_limits/create_path",
                f"/system/engine_quota/limit/organization/{organization_id}/create",
                scope="page",
            )
            page_builder.set_store("/engine_quota_limits/visible", True, scope="page")
            quota_table = page_builder.get_component("engine_quota_limits_table")
            if quota_table is not None:
                quota_table.set_property("model", quota_limit_table_model(sdk))
                quota_table.set_property(
                    "remote_service",
                    {
                        "name": "system.list_engine_quota_limits",
                        "context": {
                            "scope": "organization",
                            "subject_id": organization_id,
                        },
                    },
                )

    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    if breadcrumb_segments is not None:
        builder.set_store(
            "/organization_view/breadcrumb_segments",
            breadcrumb_segments,
            scope="page",
        )

    merge_builders(builder, page_builder)

    if page_builder.get_component("organization_view_page") is not None:
        root_ids = ["organization_view_page"]
    else:
        root_ids = [component.id for component in page_builder.get_roots() if component.id]
    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(root_ids)
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
