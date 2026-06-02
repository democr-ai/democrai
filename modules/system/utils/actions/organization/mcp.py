from __future__ import annotations

from typing import Any


def organization_mcp_rows(organization_id: int, module_sdk) -> list[dict[str, Any]]:
    links = module_sdk.models.organization_mcp.list(
        page=0,
        page_size=500,
        filters={"organization_id": organization_id},
    )
    link_rows = links["rows"]
    enabled_map: dict[int, int] = {}
    for link in link_rows:
        mcp_server_id = link.get("mcp_server_id")
        link_id = link.get("id")
        if mcp_server_id is not None and link_id is not None:
            enabled_map[int(mcp_server_id)] = int(link_id)

    listing = module_sdk.models.mcp_server_registry.list(
        page=0,
        page_size=500,
        filters={},
    )
    server_rows = listing["rows"]
    rows: list[dict[str, Any]] = []
    for server in server_rows:
        server_id = server.get("id")
        if server_id is None:
            continue
        mcp_server_id = int(server_id)
        link_id = enabled_map.get(mcp_server_id)
        rows.append(
            {
                "organization_id": organization_id,
                "mcp_server_id": mcp_server_id,
                "name": str(server.get("name") or ""),
                "transport": str(server.get("transport") or ""),
                "enabled_server": bool(server.get("enabled")),
                "enabled": bool(link_id),
                "link_id": link_id,
            }
        )
    return rows
