from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from base64 import b64decode
from base64 import b64encode
from pathlib import Path
from typing import Any

from democrai.core.infrastructure.storage.kg.providers.base import KGEdge
from democrai.core.infrastructure.storage.kg.providers.base import KGEvidence
from democrai.core.infrastructure.storage.kg.providers.base import KGNode
from democrai.core.infrastructure.storage.kg.providers.base import KGStorageProvider
from democrai.core.platform.utils.identity import denormalize_organization_id
from democrai.core.platform.utils.identity import normalize_organization_id
from democrai.core.runtime.foundation.paths import get_data_dir


def utc_epoch() -> int:
    return int(time.time())


def scoped_key(user_id: int, organization_id: int | None, record_id: str) -> str:
    organization_scope = normalize_organization_id(organization_id)
    return f"{user_id}:{organization_scope}:{record_id}"


def load_json_value(payload: str | None, default: Any) -> Any:
    if not payload:
        return default
    text = str(payload)
    if text.startswith("b64:"):
        decoded = b64decode(text[4:].encode("ascii")).decode("utf-8")
        return json.loads(decoded)
    return json.loads(text)


def load_json_object(payload: str | None) -> dict[str, Any]:
    parsed = load_json_value(payload, {})
    return parsed if isinstance(parsed, dict) else {}


def load_json_list(payload: str | None) -> list[Any]:
    parsed = load_json_value(payload, [])
    return parsed if isinstance(parsed, list) else []


def dump_json_value(value: Any) -> str:
    payload = json.dumps(value, separators=(",", ":"))
    encoded = b64encode(payload.encode("utf-8")).decode("ascii")
    return f"b64:{encoded}"


class SQLiteKGStorage(KGStorageProvider):
    """SQLite implementation for embedded knowledge-graph storage."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.path.join(get_data_dir(), "kg.sqlite")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,
        )
        self.connection.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._closed = False
        self._configure_connection()

    def _configure_connection(self) -> None:
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.connection.close()

    def run_migrations(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS kg_nodes (
                kg_key TEXT PRIMARY KEY,
                id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                node_type TEXT NOT NULL,
                properties_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                deleted_at INTEGER,
                name TEXT,
                external_ref TEXT
            );
            CREATE TABLE IF NOT EXISTS kg_evidence (
                kg_key TEXT PRIMARY KEY,
                id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                ref TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kg_edges (
                kg_key TEXT PRIMARY KEY,
                id TEXT NOT NULL,
                src_key TEXT NOT NULL,
                dst_key TEXT NOT NULL,
                src_id TEXT NOT NULL,
                dst_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                edge_type TEXT NOT NULL,
                properties_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                deleted_at INTEGER,
                weight REAL,
                confidence REAL,
                evidence_id TEXT,
                evidence_ids_json TEXT NOT NULL,
                source TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_kg_nodes_scope
                ON kg_nodes(user_id, organization_id, id, deleted_at);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_src
                ON kg_edges(user_id, organization_id, src_key, deleted_at);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_dst
                ON kg_edges(user_id, organization_id, dst_key, deleted_at);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_type
                ON kg_edges(user_id, organization_id, edge_type, deleted_at);
            """
        )

    async def _execute(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self.connection.execute,
                query,
                dict(parameters or {}),
            )

    async def _rows(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        async with self._lock:
            cursor = await asyncio.to_thread(
                self.connection.execute,
                query,
                dict(parameters or {}),
            )
            try:
                rows = await asyncio.to_thread(cursor.fetchall)
            finally:
                cursor.close()
        return [dict(row) for row in rows]

    async def add_node(self, node: KGNode) -> None:
        organization_id = normalize_organization_id(node.organization_id)
        await self._execute(
            """
            INSERT INTO kg_nodes (
                kg_key, id, user_id, organization_id, node_type, properties_json,
                created_at, updated_at, deleted_at, name, external_ref
            ) VALUES (
                :kg_key, :id, :user_id, :organization_id, :node_type, :properties_json,
                :created_at, :updated_at, :deleted_at, :name, :external_ref
            )
            ON CONFLICT(kg_key) DO UPDATE SET
                id = excluded.id,
                user_id = excluded.user_id,
                organization_id = excluded.organization_id,
                node_type = excluded.node_type,
                properties_json = excluded.properties_json,
                updated_at = excluded.updated_at,
                deleted_at = excluded.deleted_at,
                name = excluded.name,
                external_ref = excluded.external_ref
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
            SELECT id, user_id, organization_id, node_type, properties_json,
                   created_at, updated_at, deleted_at, name, external_ref
            FROM kg_nodes
            WHERE kg_key = :kg_key AND deleted_at IS NULL
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
        set_clauses = ["properties_json = :properties_json", "updated_at = :updated_at"]
        parameters: dict[str, Any] = {
            "kg_key": scoped_key(user_id, organization_id, node_id),
            "properties_json": dump_json_value(merged_properties),
            "updated_at": utc_epoch(),
        }
        for field_name, value in kwargs.items():
            if field_name in allowed_fields:
                set_clauses.append(f"{field_name} = :{field_name}")
                parameters[field_name] = value
        await self._execute(
            f"UPDATE kg_nodes SET {', '.join(set_clauses)} WHERE kg_key = :kg_key",
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
                UPDATE kg_nodes
                SET deleted_at = :deleted_at, updated_at = :deleted_at
                WHERE kg_key = :kg_key
                """,
                {"kg_key": key, "deleted_at": utc_epoch()},
            )
            return
        await self._execute("DELETE FROM kg_edges WHERE src_key = :kg_key OR dst_key = :kg_key", {"kg_key": key})
        await self._execute("DELETE FROM kg_nodes WHERE kg_key = :kg_key", {"kg_key": key})

    async def add_edge(self, edge: KGEdge) -> None:
        organization_id = normalize_organization_id(edge.organization_id)
        await self._execute(
            """
            INSERT INTO kg_edges (
                kg_key, id, src_key, dst_key, src_id, dst_id, user_id,
                organization_id, edge_type, properties_json, created_at,
                updated_at, deleted_at, weight, confidence, evidence_id,
                evidence_ids_json, source
            )
            SELECT
                :kg_key, :id, :src_key, :dst_key, :src_id, :dst_id, :user_id,
                :organization_id, :edge_type, :properties_json, :created_at,
                :updated_at, :deleted_at, :weight, :confidence, :evidence_id,
                :evidence_ids_json, :source
            WHERE EXISTS (SELECT 1 FROM kg_nodes WHERE kg_key = :src_key)
              AND EXISTS (SELECT 1 FROM kg_nodes WHERE kg_key = :dst_key)
            ON CONFLICT(kg_key) DO UPDATE SET
                id = excluded.id,
                src_key = excluded.src_key,
                dst_key = excluded.dst_key,
                src_id = excluded.src_id,
                dst_id = excluded.dst_id,
                user_id = excluded.user_id,
                organization_id = excluded.organization_id,
                edge_type = excluded.edge_type,
                properties_json = excluded.properties_json,
                updated_at = excluded.updated_at,
                deleted_at = excluded.deleted_at,
                weight = excluded.weight,
                confidence = excluded.confidence,
                evidence_id = excluded.evidence_id,
                source = excluded.source
            """,
            {
                "src_key": scoped_key(edge.user_id, edge.organization_id, edge.src),
                "dst_key": scoped_key(edge.user_id, edge.organization_id, edge.dst),
                "kg_key": scoped_key(edge.user_id, edge.organization_id, edge.id),
                "id": edge.id,
                "src_id": edge.src,
                "dst_id": edge.dst,
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
            SELECT id, src_id, dst_id, user_id, organization_id, edge_type,
                   properties_json, created_at, updated_at, deleted_at,
                   weight, confidence, evidence_id, source
            FROM kg_edges
            WHERE kg_key = :kg_key AND deleted_at IS NULL
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
        set_clauses = ["properties_json = :properties_json", "updated_at = :updated_at"]
        parameters: dict[str, Any] = {
            "kg_key": scoped_key(user_id, organization_id, edge_id),
            "properties_json": dump_json_value(merged_properties),
            "updated_at": utc_epoch(),
        }
        for field_name, value in kwargs.items():
            if field_name in allowed_fields:
                set_clauses.append(f"{field_name} = :{field_name}")
                parameters[field_name] = value
        await self._execute(
            f"UPDATE kg_edges SET {', '.join(set_clauses)} WHERE kg_key = :kg_key",
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
                UPDATE kg_edges
                SET deleted_at = :deleted_at, updated_at = :deleted_at
                WHERE kg_key = :kg_key
                """,
                {"kg_key": key, "deleted_at": utc_epoch()},
            )
            return
        await self._execute("DELETE FROM kg_edges WHERE kg_key = :kg_key", {"kg_key": key})

    async def add_evidence(self, evidence: KGEvidence) -> None:
        await self._execute(
            """
            INSERT INTO kg_evidence (
                kg_key, id, user_id, organization_id, kind, ref, payload_json, created_at
            ) VALUES (
                :kg_key, :id, :user_id, :organization_id, :kind, :ref, :payload_json, :created_at
            )
            ON CONFLICT(kg_key) DO UPDATE SET
                kind = excluded.kind,
                ref = excluded.ref,
                payload_json = excluded.payload_json
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
            "DELETE FROM kg_evidence WHERE kg_key = :kg_key",
            {"kg_key": scoped_key(user_id, organization_id, evidence_id)},
        )

    async def link_edge_to_evidence(
        self,
        user_id: int,
        edge_id: str,
        evidence_id: str,
        organization_id: int | None = None,
    ) -> None:
        key = scoped_key(user_id, organization_id, edge_id)
        rows = await self._rows(
            "SELECT evidence_ids_json FROM kg_edges WHERE kg_key = :kg_key LIMIT 1",
            {"kg_key": key},
        )
        if not rows:
            return
        evidence_ids = load_json_list(rows[0].get("evidence_ids_json"))
        if evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
        await self._execute(
            "UPDATE kg_edges SET evidence_ids_json = :evidence_ids_json WHERE kg_key = :kg_key",
            {"kg_key": key, "evidence_ids_json": dump_json_value(evidence_ids)},
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
            edge_filter = "AND e.edge_type = :edge_type"
            parameters["edge_type"] = edge_type
        rows = await self._rows(
            f"""
            SELECT e.id AS edge_id,
                   e.edge_type AS edge_type,
                   dst.id AS node_id,
                   dst.node_type AS node_type,
                   dst.name AS node_name,
                   e.properties_json AS edge_properties,
                   e.weight AS weight,
                   e.confidence AS confidence
            FROM kg_edges e
            JOIN kg_nodes dst ON dst.kg_key = e.dst_key
            WHERE e.src_key = :src_key
              AND e.user_id = :user_id
              AND e.organization_id = :organization_id
              AND e.deleted_at IS NULL
              AND dst.deleted_at IS NULL
              {edge_filter}
            ORDER BY COALESCE(e.weight, 0) DESC, COALESCE(e.confidence, 0) DESC
            LIMIT :limit
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
            """
            WITH RECURSIVE walk(node_key, node_id, depth, path) AS (
                SELECT e.dst_key, e.dst_id, 1, :start_key || '>' || e.dst_key
                FROM kg_edges e
                JOIN kg_nodes dst ON dst.kg_key = e.dst_key
                WHERE e.src_key = :start_key
                  AND e.user_id = :user_id
                  AND e.organization_id = :organization_id
                  AND e.deleted_at IS NULL
                  AND dst.deleted_at IS NULL
                UNION ALL
                SELECT e.dst_key, e.dst_id, walk.depth + 1, walk.path || '>' || e.dst_key
                FROM walk
                JOIN kg_edges e ON e.src_key = walk.node_key
                JOIN kg_nodes dst ON dst.kg_key = e.dst_key
                WHERE walk.depth < :max_depth
                  AND e.user_id = :user_id
                  AND e.organization_id = :organization_id
                  AND e.deleted_at IS NULL
                  AND dst.deleted_at IS NULL
                  AND instr(walk.path, e.dst_key) = 0
            )
            SELECT node_id, MIN(depth) AS depth
            FROM walk
            GROUP BY node_id
            ORDER BY depth ASC, node_id ASC
            """,
            {
                "start_key": scoped_key(user_id, organization_id, start_node_id),
                "user_id": user_id,
                "organization_id": normalize_organization_id(organization_id),
                "max_depth": depth,
            },
        )
        return [
            {"node_id": str(row["node_id"]), "depth": int(row["depth"])}
            for row in rows
        ]

    async def prune_orphan_nodes(
        self,
        user_id: int,
        node_ids: list[str],
        organization_id: int | None = None,
    ) -> int:
        pruned = 0
        for node_id in dict.fromkeys(str(node_id) for node_id in node_ids if node_id):
            key = scoped_key(user_id, organization_id, node_id)
            cursor = await self._execute(
                """
                DELETE FROM kg_nodes
                WHERE kg_key = :kg_key
                  AND NOT EXISTS (
                      SELECT 1 FROM kg_edges
                      WHERE deleted_at IS NULL
                        AND (src_key = :kg_key OR dst_key = :kg_key)
                  )
                """,
                {"kg_key": key},
            )
            pruned += int(getattr(cursor, "rowcount", 0) or 0)
        return pruned


__all__ = [
    "SQLiteKGStorage",
    "denormalize_organization_id",
    "load_json_object",
    "scoped_key",
    "utc_epoch",
]
