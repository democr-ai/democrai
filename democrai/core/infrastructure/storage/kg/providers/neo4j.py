from __future__ import annotations

import time
from typing import Any, Dict, Optional

from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.platform.utils.identity import denormalize_organization_id
from democrai.core.platform.utils.identity import normalize_organization_id

from .base import KGEdge, KGNode, KGStorageProvider
from .neo4j_helpers import (
    edge_user_properties,
    identity_pattern,
    node_user_properties,
    optional_scope_clause,
    sanitize_graph_name,
)
from .neo4j_query_mixins import Neo4jExtraQueriesMixin

try:
    from neo4j import AsyncGraphDatabase, GraphDatabase

    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False

# Backward-compatible helper names used in tests/imports.
_sanitize_graph_name = sanitize_graph_name
_optional_scope_clause = optional_scope_clause
_identity_pattern = identity_pattern


class Neo4jKGStorage(Neo4jExtraQueriesMixin, KGStorageProvider):
    """Neo4j implementation for Knowledge Graph storage."""

    def __init__(self, uri: str, user: str, password: str):
        if not HAS_NEO4J:
            raise ProviderNotAvailableError(
                "The 'neo4j' package is required for Neo4jKGStore. Install it with 'pip install neo4j'."
            )
        self._uri = uri
        self._auth = (user, password)
        self.driver = AsyncGraphDatabase.driver(uri, auth=self._auth)

    def run_migrations(self) -> None:
        sync_driver = GraphDatabase.driver(self._uri, auth=self._auth)
        statements = [
            "DROP CONSTRAINT kg_node_identity IF EXISTS",
            "DROP CONSTRAINT kg_evidence_identity IF EXISTS",
            "CREATE CONSTRAINT kg_node_identity IF NOT EXISTS FOR (n:KGNode) REQUIRE (n.id, n.user_id, n.organization_id) IS UNIQUE",
            "CREATE CONSTRAINT kg_evidence_identity IF NOT EXISTS FOR (e:Evidence) REQUIRE (e.id, e.user_id, e.organization_id) IS UNIQUE",
            "CREATE INDEX kg_node_scope IF NOT EXISTS FOR (n:KGNode) ON (n.user_id, n.organization_id, n.type)",
            "CREATE INDEX kg_edge_scope IF NOT EXISTS FOR ()-[r:KG_REL]-() ON (r.user_id, r.organization_id, r.type)",
        ]
        try:
            with sync_driver.session() as session:
                for statement in statements:
                    session.run(statement).consume()
        finally:
            sync_driver.close()

    async def close(self):
        await self.driver.close()

    async def add_node(self, node: KGNode) -> None:
        label = sanitize_graph_name(node.type, fallback="Entity")
        organization_id = normalize_organization_id(node.organization_id)
        async with self.driver.session() as session:
            query = (
                f"MERGE (n:KGNode:{label} {{id: $id, user_id: $user_id, organization_id: $organization_id}}) "
                "SET n += $props, "
                "    n.created_at = $created_at, "
                "    n.updated_at = $updated_at, "
                "    n.deleted_at = $deleted_at, "
                "    n.name = $name, "
                "    n.external_ref = $external_ref, "
                "    n.type = $type"
            )
            await session.run(
                query,
                id=node.id,
                user_id=node.user_id,
                organization_id=organization_id,
                props=node_user_properties(node.properties),
                created_at=node.created_at,
                updated_at=node.updated_at,
                deleted_at=node.deleted_at,
                name=node.name,
                external_ref=node.external_ref,
                type=node.type,
            )

    async def get_node(self, user_id: int, node_id: str, organization_id: Optional[int] = None) -> Optional[KGNode]:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (n:KGNode) "
                "WHERE n.id = $id AND n.user_id = $user_id"
                f"{optional_scope_clause('n', organization_id)} "
                "AND n.deleted_at IS NULL "
                "RETURN n, labels(n) as labels",
                id=node_id,
                user_id=user_id,
                organization_id=organization_scope,
            )
            record = await result.single()
            if not record:
                return None
            node_data = record["n"]
            labels = [label for label in record["labels"] if label != "KGNode"]
            props = dict(node_data)
            return KGNode(
                id=props.pop("id"),
                type=props.pop("type", labels[0] if labels else "Unknown"),
                user_id=props.pop("user_id"),
                organization_id=denormalize_organization_id(props.pop("organization_id", None)),
                properties=props,
                created_at=props.pop("created_at", int(time.time())),
                updated_at=props.pop("updated_at", int(time.time())),
                deleted_at=props.pop("deleted_at", None),
                name=props.pop("name", None),
                external_ref=props.pop("external_ref", None),
            )

    async def update_node(
        self,
        user_id: int,
        node_id: str,
        properties: Dict[str, Any],
        organization_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            query = (
                "MATCH (n:KGNode) "
                "WHERE n.id = $id AND n.user_id = $user_id"
                f"{optional_scope_clause('n', organization_id)} "
                "SET n += $props, n.updated_at = $updated_at"
            )
            params = {
                "id": node_id,
                "user_id": user_id,
                "organization_id": organization_scope,
                "props": node_user_properties(properties),
                "updated_at": int(time.time()),
            }
            for key, value in kwargs.items():
                if key in {"name", "external_ref", "deleted_at"}:
                    query += f", n.{key} = ${key}"
                    params[key] = value
            await session.run(query, **params)

    async def delete_node(self, user_id: int, node_id: str, soft: bool = True, organization_id: Optional[int] = None) -> None:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            if soft:
                await session.run(
                    "MATCH (n:KGNode) "
                    "WHERE n.id = $id AND n.user_id = $user_id"
                    f"{optional_scope_clause('n', organization_id)} "
                    "SET n.deleted_at = $deleted_at, n.updated_at = $deleted_at",
                    id=node_id,
                    user_id=user_id,
                    organization_id=organization_scope,
                    deleted_at=int(time.time()),
                )
            else:
                await session.run(
                    "MATCH (n:KGNode) "
                    "WHERE n.id = $id AND n.user_id = $user_id"
                    f"{optional_scope_clause('n', organization_id)} "
                    "DETACH DELETE n",
                    id=node_id,
                    user_id=user_id,
                    organization_id=organization_scope,
                )

    async def add_edge(self, edge: KGEdge) -> None:
        rel_type = sanitize_graph_name(edge.type, fallback="RELATED_TO")
        organization_id = normalize_organization_id(edge.organization_id)
        async with self.driver.session() as session:
            query = (
                "MATCH (src:KGNode), (dst:KGNode) "
                f"WHERE {identity_pattern('src', True)} "
                f"AND {identity_pattern('dst', True)} "
                f"MERGE (src)-[r:KG_REL:{rel_type} {{id: $id, user_id: $user_id, organization_id: $organization_id}}]->(dst) "
                "SET r += $props, "
                "    r.created_at = $created_at, "
                "    r.updated_at = $updated_at, "
                "    r.deleted_at = $deleted_at, "
                "    r.weight = $weight, "
                "    r.confidence = $confidence, "
                "    r.evidence_id = $evidence_id, "
                "    r.source = $source, "
                "    r.type = $type"
            )
            await session.run(
                query,
                src_id=edge.src,
                src_user_id=edge.user_id,
                src_organization_id=organization_id,
                dst_id=edge.dst,
                dst_user_id=edge.user_id,
                dst_organization_id=organization_id,
                id=edge.id,
                user_id=edge.user_id,
                organization_id=organization_id,
                props=edge_user_properties(edge.properties),
                created_at=edge.created_at,
                updated_at=edge.updated_at,
                deleted_at=edge.deleted_at,
                weight=edge.weight,
                confidence=edge.confidence,
                evidence_id=edge.evidence_id,
                source=edge.source,
                type=edge.type,
            )

    async def get_edge(self, user_id: int, edge_id: str, organization_id: Optional[int] = None) -> Optional[KGEdge]:
        organization_scope = normalize_organization_id(organization_id)
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (src:KGNode)-[r:KG_REL]->(dst:KGNode) "
                "WHERE r.id = $id AND r.user_id = $user_id"
                f"{optional_scope_clause('r', organization_id)} "
                "AND r.deleted_at IS NULL "
                "RETURN r, src.id as src_id, dst.id as dst_id",
                id=edge_id,
                user_id=user_id,
                organization_id=organization_scope,
            )
            record = await result.single()
            if not record:
                return None
            edge_data = record["r"]
            props = dict(edge_data)
            return KGEdge(
                id=props.pop("id"),
                src=record["src_id"],
                dst=record["dst_id"],
                type=props.pop("type", "RELATED_TO"),
                user_id=props.pop("user_id"),
                organization_id=denormalize_organization_id(props.pop("organization_id", None)),
                properties=props,
                weight=props.pop("weight", None),
                confidence=props.pop("confidence", None),
                evidence_id=props.pop("evidence_id", None),
                source=props.pop("source", None),
                created_at=props.pop("created_at", int(time.time())),
                updated_at=props.pop("updated_at", int(time.time())),
                deleted_at=props.pop("deleted_at", None),
            )


__all__ = [
    "Neo4jKGStorage",
    "_sanitize_graph_name",
    "_optional_scope_clause",
    "_identity_pattern",
    "HAS_NEO4J",
]
