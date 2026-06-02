from __future__ import annotations

from typing import Any


def organization_tool_rows(organization_id: int, module_sdk) -> list[dict[str, Any]]:
    links = module_sdk.models.organization_tool.list(
        page=0,
        page_size=500,
        filters={"organization_id": organization_id},
    )
    link_rows = links["rows"]
    enabled_map: dict[str, int] = {}
    for link in link_rows:
        tool_name = str(link.get("tool_name") or "").strip()
        link_id = link.get("id")
        if tool_name and link_id is not None:
            enabled_map[tool_name] = int(link_id)

    rows: list[dict[str, Any]] = []
    for tool in module_sdk.ai.list_tools():
        name = str(getattr(tool, "name", "") or "").strip()
        if not name:
            continue
        link_id = enabled_map.get(name)
        rows.append(
            {
                "organization_id": organization_id,
                "tool_name": name,
                "module_name": str(getattr(tool, "module_name", "") or ""),
                "description": str(getattr(tool, "description", "") or ""),
                "enabled": bool(link_id),
                "link_id": link_id,
            }
        )
    return rows
