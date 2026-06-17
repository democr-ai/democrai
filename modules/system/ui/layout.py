from democrai.sdk.client import active_sdk as sdk


async def shared_layout(builder):
    preview_id = sdk.ui.prepare_shell_surface(
        builder,
        surface_id="system_preview",
        shell_route="/system/shell",
        content_component_id="system_preview_content",
    )
    return preview_id, preview_id


async def shell_layout(builder):
    """Build the persistent shell used by system pages."""

    # 1. Define Sidebar Data & Active Detection
    groups = [
        {
            "id": "home",
            "label": "Overview",
            "icon": "ric.home-2-line",
            "path": "/system/index",
        },
        {
            "title": "User & Auth",
            "icon": "ric.user-line",
            "items": [
                {
                    "id": "user",
                    "label": "Users",
                    "path": "/system/user/list",
                    "active_path": "/system/user",
                },
                {
                    "id": "role",
                    "label": "Roles",
                    "path": "/system/role/list",
                    "active_path": "/system/role",
                },
                {
                    "id": "organization",
                    "label": "Organizations",
                    "path": "/system/organization/list",
                    "active_path": "/system/organization",
                },
            ],
        },
        {
            "title": "Ai",
            "icon": "ric.ai",
            "items": [
                {
                    "id": "models",
                    "label": "Models",
                    "path": "/system/model/list",
                    "active_path": "/system/model",
                },
                {
                    "id": "engine",
                    "label": "Engine",
                    "path": "/system/engine/list",
                    "active_path": "/system/engine",
                },
                {
                    "id": "engine_quota_counters",
                    "label": "Engine quota counters",
                    "path": "/system/engine_quota/counters/list",
                    "active_path": "/system/engine_quota/counters",
                },
                {
                    "id": "capabilities",
                    "label": "Capabilities",
                    "path": "/system/capabilities/list",
                    "active_path": "/system/capabilities",
                },
                {
                    "id": "agents",
                    "label": "Agents",
                    "path": "/system/agents/list",
                    "active_path": "/system/agents",
                },
                {
                    "id": "mcp",
                    "label": "MCP",
                    "path": "/system/mcp/list",
                    "active_path": "/system/mcp",
                },
            ],
        },
        {
            "title": "Knowledge",
            "icon": "ric.book-open-line",
            "items": [
                {
                    "id": "knowledge_extractors",
                    "label": "Extractor engines",
                    "path": "/system/knowledge/extractors/list",
                    "active_path": "/system/knowledge/extractors",
                },
                {
                    "id": "knowledge_config",
                    "label": "Knowledge config",
                    "path": "/system/knowledge/config",
                    "active_path": "/system/knowledge/config",
                },
                {
                    "id": "knowledge_extractor_config",
                    "label": "Extractor MIME",
                    "path": "/system/knowledge/extractor_config",
                    "active_path": "/system/knowledge/extractor_config",
                },
            ],
        },
        {
            "title": "Runtime",
            "icon": "ric.terminal-box-line",
            "items": [
                {
                    "id": "environment",
                    "label": "Environment",
                    "path": "/system/environment/list",
                },
            ],
        },
    ]

    tree_nodes = []
    for group in groups:
        group_node = None
        if group.get("title", None):
            group_node = {
                "id": f"group_{group['title'].lower().replace(' ', '_').replace('-', '_')}",
                "label": group["title"],
                "icon": group["icon"] if group.get("icon") else None,
                "children": [],
            }
            for item in group["items"]:
                group_node["children"].append(
                    {
                        "id": item["id"],
                        "type": "nav",
                        "label": item["label"],
                        "path": item["path"],
                        "icon": item["icon"] if item.get("icon") else None,
                        "active": sdk.ui.nav_active_path_rule(
                            item["path"], item.get("active_path", None)
                        ),
                    }
                )
        elif group.get("path", None):
            group_node = {
                "id": f"group_{group['label'].lower().replace(' ', '_').replace('-', '_')}",
                "type": "nav",
                "label": group["label"],
                "path": group["path"],
                "icon": group["icon"] if group.get("icon") else None,
                "active": sdk.ui.nav_active_path_rule(
                    group["path"], group.get("active_path", None)
                ),
            }

        if group_node:
            tree_nodes.append(group_node)

    # 2. Navigation (module-defined A2UI)
    nav_tree = sdk.ui.TreeView(
        "system_nav_tree",
        nodes=tree_nodes,
        click_action="nav",
        click_mode="single",
        selection_mode="single",
        expand_all=False,
    )
    nav_tree.set_property("full_height", True)
    nav_tree.set_property("active_as_selection", True)
    builder.add(nav_tree)

    # 3. Shell frame (centralized in SDK)
    return sdk.ui.mount_shell_frame(
        builder,
        nav_component_id="system_nav_tree",
        content_surface_id="system_preview",
        root_id="module_root",
        splitter_id="hsplit",
        nav_container_id="sys_list_container",
        content_scroll_id="scroll_preview",
        content_host_id="sys_preview",
        splitter_sizes=[150, 850],
        splitter_max_sizes=[340, 0],
        nav_padding=[18, 16, 18, 16],
        nav_max_width=340,
    )
