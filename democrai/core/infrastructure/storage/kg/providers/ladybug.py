from __future__ import annotations

import json
import logging
import os
import time
from base64 import b64decode
from base64 import b64encode
from typing import Any

from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.infrastructure.storage.kg.providers.base import KGEdge
from democrai.core.infrastructure.storage.kg.providers.base import KGEvidence
from democrai.core.infrastructure.storage.kg.providers.base import KGNode
from democrai.core.infrastructure.storage.kg.providers.base import KGStorageProvider
from democrai.core.platform.utils.identity import denormalize_organization_id
from democrai.core.platform.utils.identity import normalize_organization_id
from democrai.core.runtime.foundation.paths import get_data_dir

try:
    import ladybug

    HAS_LADYBUG = True
except ImportError:
    ladybug = None
    HAS_LADYBUG = False


def utc_epoch() -> int:
    return int(time.time())


def scoped_key(user_id: int, organization_id: int | None, record_id: str) -> str:
    organization_scope = normalize_organization_id(organization_id)
    return f"{user_id}:{organization_scope}:{record_id}"


def load_json_object(payload: str | None) -> dict[str, Any]:
    parsed = load_json_value(payload, {})
    if isinstance(parsed, dict):
        return parsed
    return {}


def load_json_list(payload: str | None) -> list[Any]:
    parsed = load_json_value(payload, [])
    if isinstance(parsed, list):
        return parsed
    return []


def load_json_value(payload: str | None, default: Any) -> Any:
    if not payload:
        return default
    text = str(payload)
    if text.startswith("b64:"):
        decoded = b64decode(text[4:].encode("ascii")).decode("utf-8")
        return json.loads(decoded)
    return json.loads(text)


def dump_json_value(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"))
    encoded = b64encode(payload.encode("utf-8")).decode("ascii")
    return f"b64:{encoded}"


class LadybugKGStorage(KGStorageProvider):
    """LadybugDB embedded implementation for knowledge-graph storage."""

    def __init__(
        self,
        db_path: str | None = None,
        *,
        max_concurrent_queries: int = 4,
    ) -> None:
        if not HAS_LADYBUG or ladybug is None:
            raise ProviderNotAvailableError(
                "The 'ladybug' package is required for LadybugKGStorage. "
                "Install it with 'pip install ladybug'."
            )
        self.db_path = db_path or os.path.join(get_data_dir(), "kg.lbug")
        self.database = self._open_database()
        self.connection = ladybug.AsyncConnection(
            self.database,
            max_concurrent_queries=max(1, max_concurrent_queries),
        )
        self._closed = False

    def _open_database(self):
        try:
            return ladybug.Database(self.db_path)
        except RuntimeError as exc:
            if not self._is_wal_replay_failure(exc):
                raise
            logging.getLogger(__name__).warning(
                "Ladybug KG WAL replay failed for %s; retrying recovery up to the "
                "last valid WAL record.",
                self.db_path,
            )
            recovered = ladybug.Database(
                self.db_path,
                throw_on_wal_replay_failure=False,
            )
            recovered.close()
            return ladybug.Database(self.db_path)

    @staticmethod
    def _is_wal_replay_failure(exc: RuntimeError) -> bool:
        message = str(exc).lower()
        return "wal" in message

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.connection.close()
        self.database.close()

    def run_migrations(self) -> None:
        connection = ladybug.Connection(self.database)
        try:
            for statement in (
                """
                CREATE NODE TABLE IF NOT EXISTS KGNode (
                    kg_key STRING PRIMARY KEY,
                    id STRING,
                    user_id INT64,
                    organization_id INT64,
                    node_type STRING,
                    properties_json STRING,
                    created_at INT64,
                    updated_at INT64,
                    deleted_at INT64,
                    name STRING,
                    external_ref STRING
                )
                """,
                """
                CREATE NODE TABLE IF NOT EXISTS Evidence (
                    kg_key STRING PRIMARY KEY,
                    id STRING,
                    user_id INT64,
                    organization_id INT64,
                    kind STRING,
                    ref STRING,
                    payload_json STRING,
                    created_at INT64
                )
                """,
                """
                CREATE REL TABLE IF NOT EXISTS KG_REL (
                    FROM KGNode TO KGNode,
                    kg_key STRING,
                    id STRING,
                    user_id INT64,
                    organization_id INT64,
                    edge_type STRING,
                    properties_json STRING,
                    created_at INT64,
                    updated_at INT64,
                    deleted_at INT64,
                    weight DOUBLE,
                    confidence DOUBLE,
                    evidence_id STRING,
                    evidence_ids_json STRING,
                    source STRING
                )
                """,
            ):
                connection.execute(statement)
        finally:
            connection.close()


    async def _execute(self, query: str, parameters: dict[str, Any] | None = None):
        if parameters is None:
            return await self.connection.execute(query)
        return await self.connection.execute(query, parameters=parameters)

    async def _rows(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = await self._execute(query, parameters)
        return list(result.rows_as_dict().get_all())

    async def add_node(self, node: KGNode) -> None:
        organization_id = normalize_organization_id(node.organization_id)
        await self._execute(
            """
            MERGE (n:KGNode {kg_key: $kg_key})
            ON CREATE SET
                n.id = $id,
                n.user_id = $user_id,
                n.organization_id = $organization_id,
                n.node_type = $node_type,
                n.properties_json = $properties_json,
                n.created_at = $created_at,
                n.updated_at = $updated_at,
                n.deleted_at = $deleted_at,
                n.name = $name,
                n.external_ref = $external_ref
            ON MATCH SET
                n.id = $id,
                n.user_id = $user_id,
                n.organization_id = $organization_id,
                n.node_type = $node_type,
                n.properties_json = $properties_json,
                n.updated_at = $updated_at,
                n.deleted_at = $deleted_at,
                n.name = $name,
                n.external_ref = $external_ref
            """,
            {
                "kg_key": scoped_key(node.user_id, node.organization_id, node.id),
                "id": node.id,
                "user_id": int(node.user_id),
                "organization_id": organization_id,
                "node_type": node.type,
                "properties_json": dump_json_value(node.properties),
                "created_at": int(node.created_at),
                "updated_at": int(node.updated_at),
                "deleted_at": node.deleted_at,
                "name": node.name,
                "external_ref": node.external_ref,
            },
        )

    async def get_node(
        self,
        user_id: int,
        node_id: str,
        organization_id: int | None = None,
    ) -> KGNode | None:
        rows = await self._rows(
            """
            MATCH (n:KGNode)
            WHERE n.kg_key = $kg_key AND n.deleted_at IS NULL
            RETURN n.id AS id,
                   n.user_id AS user_id,
                   n.organization_id AS organization_id,
                   n.node_type AS node_type,
                   n.properties_json AS properties_json,
                   n.created_at AS created_at,
                   n.updated_at AS updated_at,
                   n.deleted_at AS deleted_at,
                   n.name AS name,
                   n.external_ref AS external_ref
            LIMIT 1
            """,
            {"kg_key": scoped_key(user_id, organization_id, node_id)},
        )
        if not rows:
            return None
        row = rows[0]
        return KGNode(
            id=str(row["id"]),
            type=str(row["node_type"]),
            user_id=int(row["user_id"]),
            organization_id=denormalize_organization_id(row.get("organization_id")),
            properties=load_json_object(row.get("properties_json")),
            name=row.get("name"),
            external_ref=row.get("external_ref"),
            created_at=int(row.get("created_at") or utc_epoch()),
            updated_at=int(row.get("updated_at") or utc_epoch()),
            deleted_at=row.get("deleted_at"),
        )

    async def update_node(
        self,
        user_id: int,
        node_id: str,
        properties: dict[str, Any],
        organization_id: int | None = None,
        **kwargs,
    ) -> None:
        existing = await self.get_node(user_id, node_id, organization_id)
        if existing is None:
            return
        merged_properties = dict(existing.properties)
        merged_properties.update(properties)
        allowed_fields = {"name", "external_ref", "deleted_at"}
        set_clauses = ["n.properties_json = $properties_json", "n.updated_at = $updated_at"]
        parameters: dict[str, Any] = {
            "kg_key": scoped_key(user_id, organization_id, node_id),
            "properties_json": dump_json_value(merged_properties),
            "updated_at": utc_epoch(),
        }
        for field_name, value in kwargs.items():
            if field_name in allowed_fields:
                set_clauses.append(f"n.{field_name} = ${field_name}")
                parameters[field_name] = value
        await self._execute(
            f"""
            MATCH (n:KGNode)
            WHERE n.kg_key = $kg_key
            SET {", ".join(set_clauses)}
            """,
            parameters,
        )

    async def delete_node(
        self,
        user_id: int,
        node_id: str,
        soft: bool = True,
        organization_id: int | None = None,
    ) -> None:
        key = scoped_key(user_id, organization_id, node_id)
        if soft:
            await self._execute(
                """
                MATCH (n:KGNode)
                WHERE n.kg_key = $kg_key
                SET n.deleted_at = $deleted_at, n.updated_at = $deleted_at
                """,
                {"kg_key": key, "deleted_at": utc_epoch()},
            )
            return
        await self._execute(
            """
            MATCH (n:KGNode)
            WHERE n.kg_key = $kg_key
            DETACH DELETE n
            """,
            {"kg_key": key},
        )

    async def add_edge(self, edge: KGEdge) -> None:
        organization_id = normalize_organization_id(edge.organization_id)
        await self._execute(
            """
            MATCH (src:KGNode), (dst:KGNode)
            WHERE src.kg_key = $src_key AND dst.kg_key = $dst_key
            MERGE (src)-[r:KG_REL {kg_key: $kg_key}]->(dst)
            ON CREATE SET
                r.id = $id,
                r.user_id = $user_id,
                r.organization_id = $organization_id,
                r.edge_type = $edge_type,
                r.properties_json = $properties_json,
                r.created_at = $created_at,
                r.updated_at = $updated_at,
                r.deleted_at = $deleted_at,
                r.weight = $weight,
                r.confidence = $confidence,
                r.evidence_id = $evidence_id,
                r.evidence_ids_json = $evidence_ids_json,
                r.source = $source
            ON MATCH SET
                r.id = $id,
                r.user_id = $user_id,
                r.organization_id = $organization_id,
                r.edge_type = $edge_type,
                r.properties_json = $properties_json,
                r.updated_at = $updated_at,
                r.deleted_at = $deleted_at,
                r.weight = $weight,
                r.confidence = $confidence,
                r.evidence_id = $evidence_id,
                r.source = $source
            """,
            {
                "src_key": scoped_key(edge.user_id, edge.organization_id, edge.src),
                "dst_key": scoped_key(edge.user_id, edge.organization_id, edge.dst),
                "kg_key": scoped_key(edge.user_id, edge.organization_id, edge.id),
                "id": edge.id,
                "user_id": int(edge.user_id),
                "organization_id": organization_id,
                "edge_type": edge.type,
                "properties_json": dump_json_value(edge.properties),
                "created_at": int(edge.created_at),
                "updated_at": int(edge.updated_at),
                "deleted_at": edge.deleted_at,
                "weight": edge.weight,
                "confidence": edge.confidence,
                "evidence_id": edge.evidence_id,
                "evidence_ids_json": dump_json_value(
                    [edge.evidence_id] if edge.evidence_id else []
                ),
                "source": edge.source,
            },
        )

    async def get_edge(
        self,
        user_id: int,
        edge_id: str,
        organization_id: int | None = None,
    ) -> KGEdge | None:
        rows = await self._rows(
            """
            MATCH (src:KGNode)-[r:KG_REL]->(dst:KGNode)
            WHERE r.kg_key = $kg_key AND r.deleted_at IS NULL
            RETURN r.id AS id,
                   src.id AS src_id,
                   dst.id AS dst_id,
                   r.user_id AS user_id,
                   r.organization_id AS organization_id,
                   r.edge_type AS edge_type,
                   r.properties_json AS properties_json,
                   r.created_at AS created_at,
                   r.updated_at AS updated_at,
                   r.deleted_at AS deleted_at,
                   r.weight AS weight,
                   r.confidence AS confidence,
                   r.evidence_id AS evidence_id,
                   r.source AS source
            LIMIT 1
            """,
            {"kg_key": scoped_key(user_id, organization_id, edge_id)},
        )
        if not rows:
            return None
        row = rows[0]
        return KGEdge(
            id=str(row["id"]),
            src=str(row["src_id"]),
            dst=str(row["dst_id"]),
            type=str(row["edge_type"]),
            user_id=int(row["user_id"]),
            organization_id=denormalize_organization_id(row.get("organization_id")),
            properties=load_json_object(row.get("properties_json")),
            weight=row.get("weight"),
            confidence=row.get("confidence"),
            evidence_id=row.get("evidence_id"),
            source=row.get("source"),
            created_at=int(row.get("created_at") or utc_epoch()),
            updated_at=int(row.get("updated_at") or utc_epoch()),
            deleted_at=row.get("deleted_at"),
        )

    async def update_edge(
        self,
        user_id: int,
        edge_id: str,
        properties: dict[str, Any],
        organization_id: int | None = None,
        **kwargs,
    ) -> None:
        existing = await self.get_edge(user_id, edge_id, organization_id)
        if existing is None:
            return
        merged_properties = dict(existing.properties)
        merged_properties.update(properties)
        allowed_fields = {"weight", "confidence", "source", "evidence_id", "deleted_at"}
        set_clauses = ["r.properties_json = $properties_json", "r.updated_at = $updated_at"]
        parameters: dict[str, Any] = {
            "kg_key": scoped_key(user_id, organization_id, edge_id),
            "properties_json": dump_json_value(merged_properties),
            "updated_at": utc_epoch(),
        }
        for field_name, value in kwargs.items():
            if field_name in allowed_fields:
                set_clauses.append(f"r.{field_name} = ${field_name}")
                parameters[field_name] = value
        await self._execute(
            f"""
            MATCH ()-[r:KG_REL]->()
            WHERE r.kg_key = $kg_key
            SET {", ".join(set_clauses)}
            """,
            parameters,
        )

    async def delete_edge(
        self,
        user_id: int,
        edge_id: str,
        soft: bool = True,
        organization_id: int | None = None,
    ) -> None:
        key = scoped_key(user_id, organization_id, edge_id)
        if soft:
            await self._execute(
                """
                MATCH ()-[r:KG_REL]->()
                WHERE r.kg_key = $kg_key
                SET r.deleted_at = $deleted_at, r.updated_at = $deleted_at
                """,
                {"kg_key": key, "deleted_at": utc_epoch()},
            )
            return
        await self._execute(
            """
            MATCH ()-[r:KG_REL]->()
            WHERE r.kg_key = $kg_key
            DELETE r
            """,
            {"kg_key": key},
        )

    async def add_evidence(self, evidence: KGEvidence) -> None:
        await self._execute(
            """
            MERGE (e:Evidence {kg_key: $kg_key})
            ON CREATE SET
                e.id = $id,
                e.user_id = $user_id,
                e.organization_id = $organization_id,
                e.kind = $kind,
                e.ref = $ref,
                e.payload_json = $payload_json,
                e.created_at = $created_at
            ON MATCH SET
                e.kind = $kind,
                e.ref = $ref,
                e.payload_json = $payload_json
            """,
            {
                "kg_key": scoped_key(evidence.user_id, evidence.organization_id, evidence.id),
                "id": evidence.id,
                "user_id": int(evidence.user_id),
                "organization_id": normalize_organization_id(evidence.organization_id),
                "kind": evidence.kind,
                "ref": evidence.ref,
                "payload_json": dump_json_value(evidence.payload),
                "created_at": int(evidence.created_at),
            },
        )

    async def delete_evidence(
        self,
        user_id: int,
        evidence_id: str,
        organization_id: int | None = None,
    ) -> None:
        await self._execute(
            """
            MATCH (e:Evidence)
            WHERE e.kg_key = $kg_key
            DETACH DELETE e
            """,
            {"kg_key": scoped_key(user_id, organization_id, evidence_id)},
        )

    async def link_edge_to_evidence(
        self,
        user_id: int,
        edge_id: str,
        evidence_id: str,
        organization_id: int | None = None,
    ) -> None:
        rows = await self._rows(
            """
            MATCH ()-[r:KG_REL]->()
            WHERE r.kg_key = $kg_key
            RETURN r.evidence_ids_json AS evidence_ids_json
            LIMIT 1
            """,
            {"kg_key": scoped_key(user_id, organization_id, edge_id)},
        )
        if not rows:
            return
        evidence_ids = load_json_list(rows[0].get("evidence_ids_json"))
        if evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
        await self._execute(
            """
            MATCH ()-[r:KG_REL]->()
            WHERE r.kg_key = $kg_key
            SET r.evidence_ids_json = $evidence_ids_json
            """,
            {
                "kg_key": scoped_key(user_id, organization_id, edge_id),
                "evidence_ids_json": dump_json_value(evidence_ids),
            },
        )

    async def get_neighbors(
        self,
        user_id: int,
        node_id: str,
        edge_type: str | None = None,
        limit: int = 10,
        organization_id: int | None = None,
    ) -> list[dict[str, Any]]:
        parameters: dict[str, Any] = {
            "src_key": scoped_key(user_id, organization_id, node_id),
            "user_id": user_id,
            "organization_id": normalize_organization_id(organization_id),
            "limit": limit,
        }
        edge_filter = ""
        if edge_type:
            edge_filter = "AND r.edge_type = $edge_type"
            parameters["edge_type"] = edge_type
        rows = await self._rows(
            f"""
            MATCH (src:KGNode)-[r:KG_REL]->(dst:KGNode)
            WHERE src.kg_key = $src_key
              AND r.user_id = $user_id
              AND r.organization_id = $organization_id
              AND r.deleted_at IS NULL
              AND dst.deleted_at IS NULL
              {edge_filter}
            RETURN r.id AS edge_id,
                   r.edge_type AS edge_type,
                   dst.id AS node_id,
                   dst.node_type AS node_type,
                   dst.name AS node_name,
                   r.properties_json AS edge_properties,
                   r.weight AS weight,
                   r.confidence AS confidence
            ORDER BY COALESCE(r.weight, 0) DESC, COALESCE(r.confidence, 0) DESC
            LIMIT $limit
            """,
            parameters,
        )
        for row in rows:
            row["edge_properties"] = load_json_object(row.get("edge_properties"))
        return rows

    async def traversal(
        self,
        user_id: int,
        start_node_id: str,
        max_depth: int = 2,
        organization_id: int | None = None,
    ) -> list[dict[str, Any]]:
        depth = max(1, max_depth)
        rows = await self._rows(
            f"""
            MATCH (start:KGNode)-[rels:KG_REL*1..{depth}]->(node:KGNode)
            WHERE start.kg_key = $start_key
              AND node.user_id = $user_id
              AND node.organization_id = $organization_id
              AND node.deleted_at IS NULL
            RETURN node.id AS node_id, length(rels) AS depth
            ORDER BY depth ASC, node_id ASC
            """,
            {
                "start_key": scoped_key(user_id, organization_id, start_node_id),
                "user_id": user_id,
                "organization_id": normalize_organization_id(organization_id),
            },
        )
        deduped: dict[str, int] = {}
        for row in rows:
            node_id = str(row["node_id"])
            row_depth = int(row["depth"])
            current_depth = deduped.get(node_id)
            if current_depth is None or row_depth < current_depth:
                deduped[node_id] = row_depth
        return [
            {"node_id": node_id, "depth": row_depth}
            for node_id, row_depth in sorted(deduped.items(), key=lambda item: (item[1], item[0]))
        ]

    async def prune_orphan_nodes(
        self,
        user_id: int,
        node_ids: list[str],
        organization_id: int | None = None,
    ) -> int:
        pruned = 0
        for node_id in dict.fromkeys(str(node_id) for node_id in node_ids if node_id):
            rows = await self._rows(
                """
                MATCH (n:KGNode)
                WHERE n.kg_key = $kg_key
                OPTIONAL MATCH (n)-[r:KG_REL]-()
                WHERE r.deleted_at IS NULL
                WITH n, count(r) AS active_edges
                WHERE active_edges = 0
                DETACH DELETE n
                RETURN count(n) AS deleted_count
                """,
                {"kg_key": scoped_key(user_id, organization_id, node_id)},
            )
            pruned += int(rows[0].get("deleted_count") or 0) if rows else 0
        return pruned


__all__ = [
    "HAS_LADYBUG",
    "LadybugKGStorage",
    "denormalize_organization_id",
    "load_json_object",
    "scoped_key",
    "utc_epoch",
]
