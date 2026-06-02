from __future__ import annotations

from typing import Any


def organization_agent_rows(organization_id: int, module_sdk) -> list[dict[str, Any]]:
    links = module_sdk.models.organization_agent.list(
        page=0,
        page_size=500,
        filters={"organization_id": organization_id},
    )
    link_rows = links["rows"]
    enabled_map: dict[str, int] = {}
    for link in link_rows:
        agent_name = str(link.get("agent_name") or "").strip()
        link_id = link.get("id")
        if agent_name and link_id is not None:
            enabled_map[agent_name] = int(link_id)

    rows: list[dict[str, Any]] = []
    for agent in module_sdk.ai.list_agents():
        name = str(getattr(agent, "name", "") or "").strip()
        if not name:
            continue
        link_id = enabled_map.get(name)
        rows.append(
            {
                "organization_id": organization_id,
                "agent_name": name,
                "module_name": str(getattr(agent, "module_name", "") or ""),
                "description": str(getattr(agent, "description", "") or ""),
                "enabled": bool(link_id),
                "link_id": link_id,
            }
        )
    return rows
