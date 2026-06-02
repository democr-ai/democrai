from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from democrai.core.platform.utils.identity import normalize_organization_id

from .neo4j_helpers import edge_user_properties
from .neo4j_helpers import optional_scope_clause
from .neo4j_helpers import sanitize_graph_name


class Neo4jExtraQueriesMixin:
    async def update_edge(
        self,
        user_id: int,
        edge_id: str,
        properties: Dict[str, Any],
        organization_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            query = (
                "MATCH ()-[r:KG_REL]->() "
                "WHERE r.id = $id AND r.user_id = $user_id"
                f"{optional_scope_clause('r', organization_id)} "
                "SET r += $props, r.updated_at = $updated_at"
            )
            params = {
                "id": edge_id,
                "user_id": user_id,
                "organization_id": organization_scope,
                "props": edge_user_properties(properties),
                "updated_at": int(time.time()),
            }
            for key, value in kwargs.items():
                if key in {"weight", "confidence", "source", "evidence_id", "deleted_at"}:
                    query += f", r.{key} = ${key}"
                    params[key] = value
            await session.run(query, **params)

    async def delete_edge(
        self,
        user_id: int,
        edge_id: str,
        soft: bool = True,
        organization_id: Optional[int] = None,
    ) -> None:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            if soft:
                await session.run(
                    "MATCH ()-[r:KG_REL]->() "
                    "WHERE r.id = $id AND r.user_id = $user_id"
                    f"{optional_scope_clause('r', organization_id)} "
                    "SET r.deleted_at = $deleted_at, r.updated_at = $deleted_at",
                    id=edge_id,
                    user_id=user_id,
                    organization_id=organization_scope,
                    deleted_at=int(time.time()),
                )
            else:
                await session.run(
                    "MATCH ()-[r:KG_REL]->() "
                    "WHERE r.id = $id AND r.user_id = $user_id"
                    f"{optional_scope_clause('r', organization_id)} "
                    "DELETE r",
                    id=edge_id,
                    user_id=user_id,
                    organization_id=organization_scope,
                )

    async def add_evidence(self, evidence) -> None:
        organization_id = normalize_organization_id(evidence.organization_id)
        async with self.driver.session() as session:
            query = (
                "MERGE (e:Evidence {id: $id, user_id: $user_id, organization_id: $organization_id}) "
                "SET e.kind = $kind, "
                "    e.ref = $ref, "
                "    e.payload = $payload, "
                "    e.created_at = $created_at"
            )
            await session.run(
                query,
                id=evidence.id,
                user_id=evidence.user_id,
                organization_id=organization_id,
                kind=evidence.kind,
                ref=evidence.ref,
                payload=json.dumps(evidence.payload),
                created_at=evidence.created_at,
            )

    async def delete_evidence(
        self,
        user_id: int,
        evidence_id: str,
        organization_id: Optional[int] = None,
    ) -> None:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            await session.run(
                "MATCH (e:Evidence) "
                "WHERE e.id = $id AND e.user_id = $user_id"
                f"{optional_scope_clause('e', organization_id)} "
                "DETACH DELETE e",
                id=evidence_id,
                user_id=user_id,
                organization_id=organization_scope,
            )

    async def link_edge_to_evidence(self, user_id: int, edge_id: str, evidence_id: str, organization_id: Optional[int] = None) -> None:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            query = (
                "MATCH (e:Evidence) "
                "WHERE e.id = $ev_id AND e.user_id = $user_id"
                f"{optional_scope_clause('e', organization_id)} "
                "MATCH ()-[r:KG_REL]->() "
                "WHERE r.id = $edge_id AND r.user_id = $user_id"
                f"{optional_scope_clause('r', organization_id)} "
                "SET r.evidence_ids = CASE "
                "WHEN $ev_id IN coalesce(r.evidence_ids, []) "
                "THEN coalesce(r.evidence_ids, []) "
                "ELSE coalesce(r.evidence_ids, []) + $ev_id END"
            )
            await session.run(
                query,
                ev_id=evidence_id,
                edge_id=edge_id,
                user_id=user_id,
                organization_id=organization_scope,
            )

    async def get_neighbors(
        self,
        user_id: int,
        node_id: str,
        edge_type: Optional[str] = None,
        limit: int = 10,
        organization_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            rel_match = ""
            if edge_type:
                rel_match = f":{sanitize_graph_name(edge_type, fallback='RELATED_TO')}"
            query = (
                f"MATCH (src:KGNode {{id: $id, user_id: $user_id}})-[r:KG_REL{rel_match}]->(dst:KGNode) "
                "WHERE r.deleted_at IS NULL AND dst.deleted_at IS NULL AND r.user_id = $user_id"
                f"{optional_scope_clause('src', organization_id)}"
                f"{optional_scope_clause('r', organization_id)}"
                f"{optional_scope_clause('dst', organization_id)} "
                "RETURN r.id as edge_id, coalesce(r.type, type(r)) as edge_type, dst.id as node_id, "
                "dst.type as node_type, dst.name as node_name, properties(r) as edge_properties, "
                "r.weight as weight, r.confidence as confidence "
                "ORDER BY coalesce(r.weight, 0) DESC, coalesce(r.confidence, 0) DESC LIMIT $limit"
            )
            result = await session.run(
                query,
                id=node_id,
                user_id=user_id,
                organization_id=organization_scope,
                limit=limit,
            )
            return [dict(record) for record in await result.data()]

    async def traversal(
        self,
        user_id: int,
        start_node_id: str,
        max_depth: int = 2,
        organization_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        depth = max(1, max_depth)
        organization_scope = normalize_organization_id(organization_id)
        scope_clause = optional_scope_clause("start", organization_scope)
        query = (
            f"MATCH (start:KGNode {{id: $id, user_id: $user_id}}){scope_clause}"
            f"-[rels:KG_REL*1..{depth}]->(node:KGNode) "
            "WHERE all(r in rels WHERE r.deleted_at IS NULL AND r.user_id = $user_id"
            + optional_scope_clause("r", organization_scope)
            + ") "
            "AND node.deleted_at IS NULL AND node.user_id = $user_id"
            + optional_scope_clause("node", organization_scope)
            + " "
            "RETURN node.id as node_id, min(size(rels)) as depth "
            "ORDER BY depth ASC, node_id ASC"
        )
        async with self.driver.session() as session:
            result = await session.run(
                query,
                id=start_node_id,
                user_id=user_id,
                organization_id=organization_scope,
            )
            return await result.data()

    async def prune_orphan_nodes(
        self,
        user_id: int,
        node_ids: list[str],
        organization_id: Optional[int] = None,
    ) -> int:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (n:KGNode) "
                "WHERE n.id IN $ids AND n.user_id = $user_id"
                f"{optional_scope_clause('n', organization_id)} "
                "AND NOT EXISTS { MATCH (n)-[r:KG_REL]-() WHERE r.deleted_at IS NULL } "
                "WITH collect(n) AS nodes "
                "FOREACH (node IN nodes | DETACH DELETE node) "
                "RETURN size(nodes) AS deleted_count",
                ids=list(dict.fromkeys(str(node_id) for node_id in node_ids if node_id)),
                user_id=user_id,
                organization_id=organization_scope,
            )
            record = await result.single()
            return int(record["deleted_count"] or 0) if record else 0
