from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk


_NAV_GROUPS = [
    {
        "title": "Start",
        "icon": "ric.home-2-line",
        "items": [
            {"id": "home", "label": "Overview", "path": "/components/index"},
        ],
    },
    {
        "title": "LAYOUT",
        "icon": "ric.layout-2-fill",
        "items": [
            {"id": "header", "label": "Header", "path": "/components/_layout/header"},
            {"id": "row", "label": "Row", "path": "/components/_layout/row"},
            {"id": "column", "label": "Column", "path": "/components/_layout/column"},
            {"id": "flex", "label": "FlexContainer", "path": "/components/_layout/flex"},
            {"id": "sidebar", "label": "Sidebar", "path": "/components/_layout/sidebar"},
            {
                "id": "sidebar_content",
                "label": "Shell: Sidebar + Content",
                "path": "/components/_layout/sidebar_content",
            },
            {
                "id": "sidebar_content_header",
                "label": "Shell: Sidebar + Content Header",
                "path": "/components/_layout/sidebar_content_header",
            },
            {
                "id": "sidebar_split_content",
                "label": "Shell: Sidebar + Split Content",
                "path": "/components/_layout/sidebar_split_content",
            },
        ],
    },
    {
        "title": "Content",
        "icon": "ric.kanban-view",
        "items": [
            {"id": "text", "label": "Typography", "path": "/components/_content/text"},
            {
                "id": "breadcrumb",
                "label": "Breadcrumb",
                "path": "/components/_content/breadcrumb",
            },
            {"id": "image", "label": "Image", "path": "/components/_content/image"},
            {"id": "video", "label": "Video", "path": "/components/_content/video"},
            {"id": "audio", "label": "Audio", "path": "/components/_content/audio"},
            {"id": "qrcode", "label": "QrCode", "path": "/components/_content/qrcode"},
            {
                "id": "progress",
                "label": "Progress",
                "path": "/components/_content/progress",
            },
            {
                "id": "status",
                "label": "Status && Badge",
                "path": "/components/_content/status",
            },
            {"id": "icons", "label": "Icons", "path": "/components/_content/icons"},
        ],
    },
    {
        "title": "Complex elements",
        "icon": "ric.brackets-fill",
        "items": [
            {"id": "treeview", "label": "Tree View", "path": "/components/_complex/treeview"},
            {
                "id": "descriptions",
                "label": "Descriptions",
                "path": "/components/_complex/descriptions",
            },
            {
                "id": "accordion",
                "label": "Accordion",
                "path": "/components/_complex/accordion",
            },
            {"id": "carousel", "label": "Carousel", "path": "/components/_complex/carousel"},
            {"id": "list", "label": "List", "path": "/components/_complex/list"},
            {
                "id": "datatable",
                "label": "Data Table",
                "path": "/components/_complex/datatable",
            },
            {"id": "card", "label": "Card", "path": "/components/_complex/card"},
            {"id": "codediff", "label": "Code diff", "path": "/components/_complex/codediff"},
            {"id": "wizard", "label": "Wizard", "path": "/components/_complex/wizard"},
            {"id": "grid", "label": "Grid", "path": "/components/_complex/grid"},
            {"id": "tabs", "label": "Tabs", "path": "/components/_complex/tabs"},
            {"id": "calendar", "label": "Calendar", "path": "/components/_complex/calendar"},
        ],
    },
    {
        "title": "Forms",
        "icon": "ric.input-field",
        "items": [
            {"id": "button", "label": "Buttons", "path": "/components/_forms/buttons"},
            {"id": "textfield", "label": "Text", "path": "/components/_forms/text"},
            {"id": "select", "label": "Select", "path": "/components/_forms/select"},
            {"id": "tags", "label": "Tags", "path": "/components/_forms/tags"},
            {
                "id": "editable_list",
                "label": "EditableList",
                "path": "/components/_forms/editable_list",
            },
            {"id": "textarea", "label": "Textarea", "path": "/components/_forms/textarea"},
            {"id": "radio", "label": "Radio", "path": "/components/_forms/radio"},
            {"id": "toggle", "label": "Toggle", "path": "/components/_forms/toggle"},
            {"id": "checkbox", "label": "Checkbox", "path": "/components/_forms/checkbox"},
            {"id": "date", "label": "DateTime", "path": "/components/_forms/datetime"},
            {"id": "model", "label": "Model", "path": "/components/_forms/model"},
            {
                "id": "media_upload",
                "label": "Media Upload",
                "path": "/components/_forms/media_upload",
            },
            {
                "id": "audio_recorder",
                "label": "Audio Recorder",
                "path": "/components/_forms/audio_recorder",
            },
        ],
    },
    {
        "title": "Effects",
        "icon": "ric.brain-ai-3-fill",
        "items": [
            {"id": "toast", "label": "Toast", "path": "/components/_effects/toast"},
            {"id": "drawer", "label": "Drawer", "path": "/components/_effects/drawer"},
            {"id": "modal", "label": "Modal", "path": "/components/_effects/modal"},
            {
                "id": "animation",
                "label": "Animation",
                "path": "/components/_effects/animation",
            },
            {"id": "copy", "label": "Copy to clipboard", "path": "/components/_effects/copy"},
            {
                "id": "dynamic",
                "label": "Dynamic Containers",
                "path": "/components/_effects/dynamic",
            },
            {"id": "yaml", "label": "Yaml Builder", "path": "/components/_effects/yaml"},
            {
                "id": "background_task",
                "label": "Background Task",
                "path": "/components/_effects/background_task",
            },
        ],
    },
    {
        "title": "Charts & Diagrams",
        "icon": "ric.bar-chart-fill",
        "items": [
            {"id": "base", "label": "Base", "path": "/components/_charts/base"},
            {
                "id": "diagram",
                "label": "Sequence Diagram",
                "path": "/components/_charts/diagram",
            },
            {"id": "gantt", "label": "Gantt", "path": "/components/_charts/gantt"},
            {"id": "git", "label": "Git", "path": "/components/_charts/git"},
        ],
    },
    {
        "title": "Ai",
        "icon": "ric.ai",
        "items": [
            {"id": "input", "label": "Input", "path": "/components/_ai/input"},
            {"id": "chat", "label": "Chat", "path": "/components/_ai/chat"},
        ],
    },
    {
        "title": "Flow & Effects",
        "icon": "ric.flow-chart",
        "items": [
            {
                "id": "external_path",
                "label": "External Approval Path",
                "path": "/components/_flow/external_path",
            },
            {
                "id": "external_url",
                "label": "External Approval Url",
                "path": "/components/_flow/external_url",
            },
            {
                "id": "page_state",
                "label": "Page state management",
                "path": "/components/_flow/page_state",
            },
            {
                "id": "global_state",
                "label": "Global state management",
                "path": "/components/_flow/global_state",
            },
            {
                "id": "client_runtime",
                "label": "Client Runtime Query",
                "path": "/components/_flow/client_runtime",
            },
            {
                "id": "stream_binding",
                "label": "StreamBinding",
                "path": "/components/_flow/stream_binding",
            },
            {"id": "orm", "label": "ORM management", "path": "/components/_flow/orm"},
            {"id": "events", "label": "Events", "path": "/components/_flow/events"},
            {"id": "hooks", "label": "Hooks", "path": "/components/_flow/hooks"},
            {
                "id": "permission",
                "label": "Permissions and visibility",
                "path": "/components/_flow/permission",
            },
        ],
    },
]


def _navigation_nodes() -> list[dict]:
    tree_nodes = []
    for group in _NAV_GROUPS:
        group_id = group["title"].lower().replace(" ", "_").replace("-", "_")
        group_node = {
            "id": f"group_{group_id}",
            "label": group["title"],
            "icon": group.get("icon"),
            "children": [],
        }
        for item in group["items"]:
            group_node["children"].append(
                {
                    "id": item["id"],
                    "type": "nav",
                    "label": item["label"],
                    "path": item["path"],
                    "icon": item.get("icon"),
                    "active": sdk.ui.nav_active_path_rule(item["path"]),
                }
            )
        tree_nodes.append(group_node)
    return tree_nodes


async def shared_layout(builder):
    """Prepare preview-only content for the components sub-surface."""
    builder.set_surface("components_preview", shell_route="/components/shell")
    builder.merge(sdk.ui.load("ui/yaml/layout_preview_surface"), components=True)
    return "components_preview_content", "components_preview_content"


async def shell_layout(builder):
    """Build the persistent shell used by components pages."""
    builder.merge(sdk.ui.load("ui/yaml/layout_shell"), components=True)
    builder.set_data("components_layout/nav_tree", _navigation_nodes())
    return "module_root", "comp_preview"
