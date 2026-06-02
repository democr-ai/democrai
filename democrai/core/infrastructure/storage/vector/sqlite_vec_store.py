from __future__ import annotations

import array
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

import sqlite_vec

from democrai.core.infrastructure.database.sqlite_tuning import apply_sqlite_pragmas_to_connection
from democrai.core.infrastructure.storage.vector.base import Capability
from democrai.core.infrastructure.storage.vector.base import Filter
from democrai.core.infrastructure.storage.vector.base import IndexSpec
from democrai.core.infrastructure.storage.vector.base import Match
from democrai.core.infrastructure.storage.vector.base import Metric
from democrai.core.infrastructure.storage.vector.base import Op
from democrai.core.infrastructure.storage.vector.base import Predicate
from democrai.core.infrastructure.storage.vector.base import ProviderInfo
from democrai.core.infrastructure.storage.vector.base import Query
from democrai.core.infrastructure.storage.vector.base import UserScope
from democrai.core.infrastructure.storage.vector.base import VectorDoc
from democrai.core.infrastructure.storage.vector.base import VectorProvider
from democrai.core.infrastructure.storage.vector.base import normalize_score
from democrai.core.infrastructure.storage.vector.base import physical_index_name


def _load_sqlite_vec_on_connection(conn: sqlite3.Connection) -> tuple[bool, str | None]:
    try:
        sqlite_vec.load(conn)
    except sqlite3.Error as exc:
        return False, str(exc)
    except OSError as exc:
        return False, str(exc)
    return True, None


def sqlite_vec_available() -> tuple[bool, str | None]:
    conn = sqlite3.connect(":memory:")
    try:
        return _load_sqlite_vec_on_connection(conn)
    finally:
        conn.close()


def _scope_organization_id(scope: UserScope) -> int:
    # 0 = No organization, positive integers for valid organization IDs, negative integers for invalid/missing organization IDs
    return int(scope.organization_id or 0)


def _index_table_name(spec: IndexSpec, index_prefix: str = "democrai") -> str:
    return physical_index_name(spec, index_prefix)


def _doc_key(scope: UserScope, doc_id: str) -> str:
    logical_key = f"{int(scope.user_id)}\x1f{_scope_organization_id(scope)}\x1f{doc_id}"
    return hashlib.sha256(logical_key.encode("utf-8")).hexdigest()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _serialize_vector(vector: Sequence[float]) -> bytes:
    return sqlite_vec.serialize_float32([float(item) for item in vector])


def _deserialize_vector(value: bytes) -> list[float]:
    return array.array("f", value).tolist()


def _metric_name(metric: Metric) -> str:
    if metric == Metric.COSINE:
        return "cosine"
    if metric == Metric.L2:
        return "l2"
    raise ValueError(f"Unsupported vector metric for sqlite-vec: {metric}")


def _metadata_value(metadata: Mapping[str, Any], key: str) -> Any:
    return metadata.get(key)


def _predicate_matches(metadata: Mapping[str, Any], pred: Predicate) -> bool:
    actual = _metadata_value(metadata, pred.key)
    if pred.op == Op.EQ:
        return actual == pred.value
    if pred.op == Op.IN:
        values = pred.value if isinstance(pred.value, (list, tuple, set)) else [pred.value]
        return actual in values
    if pred.op in {Op.LT, Op.LTE, Op.GT, Op.GTE}:
        if actual is None:
            return False
        if pred.op == Op.LT:
            return actual < pred.value
        if pred.op == Op.LTE:
            return actual <= pred.value
        if pred.op == Op.GT:
            return actual > pred.value
        return actual >= pred.value
    raise ValueError(f"Unsupported predicate op: {pred.op}")


def _filter_item_matches(metadata: Mapping[str, Any], item: Filter | Predicate) -> bool:
    if isinstance(item, Predicate):
        return _predicate_matches(metadata, item)
    return _filter_matches(metadata, item)


def _filter_matches(metadata: Mapping[str, Any], flt: Filter | None) -> bool:
    if flt is None:
        return True
    if flt.pred is not None:
        return _predicate_matches(metadata, flt.pred)
    if flt.and_:
        return all(_filter_item_matches(metadata, item) for item in flt.and_)
    if flt.or_:
        return any(_filter_item_matches(metadata, item) for item in flt.or_)
    return True


def _score_from_distance(metric: Metric, distance: float) -> float:
    if metric == Metric.COSINE:
        return max(0.0, min(1.0, 1.0 - (distance / 2.0)))
    return normalize_score(metric, distance)


class SQLiteVecVectorProvider(VectorProvider):
    def __init__(self, db_path: str, index_prefix: str = "democrai"):
        self.db_path = db_path
        self.index_prefix = index_prefix

    def _get_connection(self) -> sqlite3.Connection:
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        apply_sqlite_pragmas_to_connection(conn)
        conn.row_factory = sqlite3.Row
        ok, err = _load_sqlite_vec_on_connection(conn)
        if not ok:
            conn.close()
            raise RuntimeError(f"sqlite-vec extension unavailable: {err or 'unknown error'}")
        return conn

    async def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="sqlite-vec-embedded",
            version=getattr(sqlite_vec, "__version__", None),
            capabilities=Capability.FILTER_EQ
            | Capability.FILTER_IN
            | Capability.FILTER_RANGE
            | Capability.FILTER_AND
            | Capability.FILTER_OR
            | Capability.UPSERT_IDEMPOTENT
            | Capability.BULK_UPSERT
            | Capability.USER_SCOPED
            | Capability.DELETE_BY_FILTER
            | Capability.RETURN_VECTORS
            | Capability.REBUILD_INDEX,
        )

    def _ensure_metadata_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_indices (
              tenant_id TEXT NOT NULL,
              app_id TEXT NOT NULL,
              name TEXT NOT NULL,
              dim INTEGER NOT NULL,
              metric TEXT NOT NULL,
              model_id TEXT,
              model_version TEXT,
              table_name TEXT NOT NULL,
              PRIMARY KEY (tenant_id, app_id, name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_payloads (
              id TEXT NOT NULL,
              tenant_id TEXT NOT NULL,
              app_id TEXT NOT NULL,
              index_name TEXT NOT NULL,
              user_id INTEGER NOT NULL,
              organization_id INTEGER NOT NULL,
              metadata TEXT NOT NULL,
              vector BLOB NOT NULL,
              timestamp INTEGER NOT NULL,
              PRIMARY KEY (id, tenant_id, app_id, index_name, user_id, organization_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vector_payloads_scope
            ON vector_payloads (tenant_id, app_id, index_name, user_id, organization_id)
            """
        )

    def _ensure_index_schema(self, conn: sqlite3.Connection, spec: IndexSpec) -> str:
        table_name = _index_table_name(spec, self.index_prefix)
        self._ensure_metadata_schema(conn)
        existing = conn.execute(
            """
            SELECT dim, metric, model_id, model_version, table_name
            FROM vector_indices
            WHERE tenant_id = ? AND app_id = ? AND name = ?
            """,
            (spec.tenant_id, spec.app_id, spec.name),
        ).fetchone()
        if existing is not None:
            if int(existing["dim"]) != int(spec.dim) or str(existing["metric"]) != spec.metric.value:
                raise ValueError(
                    "Vector index spec mismatch for "
                    f"{spec.tenant_id}:{spec.app_id}:{spec.name}"
                )
            return str(existing["table_name"])
        metric_name = _metric_name(spec.metric)
        quoted_table = _quote_identifier(table_name)
        if not _table_exists(conn, table_name):
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE {quoted_table} USING vec0(
                  doc_key TEXT PRIMARY KEY,
                  user_id INTEGER PARTITION KEY,
                  organization_id INTEGER PARTITION KEY,
                  embedding FLOAT[{int(spec.dim)}] distance_metric={metric_name},
                  +doc_id TEXT,
                  +metadata TEXT
                )
                """
            )
        conn.execute(
            """
            INSERT INTO vector_indices (
              tenant_id, app_id, name, dim, metric, model_id, model_version, table_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                spec.tenant_id,
                spec.app_id,
                spec.name,
                int(spec.dim),
                spec.metric.value,
                spec.embedding_model_id,
                spec.embedding_model_version,
                table_name,
            ),
        )
        return table_name

    async def ensure_index(self, spec: IndexSpec) -> None:
        with self._get_connection() as conn:
            self._ensure_index_schema(conn, spec)

    async def drop_index(self, spec: IndexSpec) -> None:
        table_name = _index_table_name(spec, self.index_prefix)
        with self._get_connection() as conn:
            self._ensure_metadata_schema(conn)
            row = conn.execute(
                """
                SELECT table_name FROM vector_indices
                WHERE tenant_id = ? AND app_id = ? AND name = ?
                """,
                (spec.tenant_id, spec.app_id, spec.name),
            ).fetchone()
            if row is not None:
                table_name = str(row["table_name"])
            conn.execute(f"DROP TABLE IF EXISTS {_quote_identifier(table_name)}")
            conn.execute(
                "DELETE FROM vector_indices WHERE tenant_id = ? AND app_id = ? AND name = ?",
                (spec.tenant_id, spec.app_id, spec.name),
            )
            conn.execute(
                "DELETE FROM vector_payloads WHERE tenant_id = ? AND app_id = ? AND index_name = ?",
                (spec.tenant_id, spec.app_id, spec.name),
            )

    async def upsert(
        self, scope: UserScope, spec: IndexSpec, docs: Sequence[VectorDoc]
    ) -> None:
        if not docs:
            return
        now = int(time.time())
        organization_id = _scope_organization_id(scope)
        with self._get_connection() as conn:
            table_name = self._ensure_index_schema(conn, spec)
            quoted_table = _quote_identifier(table_name)
            for doc in docs:
                doc_key = _doc_key(scope, doc.id)
                vector = _serialize_vector(doc.vector)
                metadata = json.dumps(dict(doc.metadata or {}), separators=(",", ":"))
                cursor = conn.execute(
                    f"""
                    UPDATE {quoted_table}
                    SET embedding = ?, doc_id = ?, metadata = ?
                    WHERE doc_key = ? AND user_id = ? AND organization_id = ?
                    """,
                    (vector, doc.id, metadata, doc_key, int(scope.user_id), organization_id),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        f"""
                        INSERT INTO {quoted_table} (
                          doc_key, user_id, organization_id, embedding, doc_id, metadata
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (doc_key, int(scope.user_id), organization_id, vector, doc.id, metadata),
                    )
                conn.execute(
                    """
                    INSERT INTO vector_payloads (
                      id, tenant_id, app_id, index_name, user_id, organization_id,
                      metadata, vector, timestamp
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id, tenant_id, app_id, index_name, user_id, organization_id)
                    DO UPDATE SET
                      metadata = excluded.metadata,
                      vector = excluded.vector,
                      timestamp = excluded.timestamp
                    """,
                    (
                        doc.id,
                        spec.tenant_id,
                        spec.app_id,
                        spec.name,
                        int(scope.user_id),
                        organization_id,
                        metadata,
                        vector,
                        now,
                    ),
                )

    async def delete_ids(
        self, scope: UserScope, spec: IndexSpec, ids: Sequence[str]
    ) -> int:
        if not ids:
            return 0
        organization_id = _scope_organization_id(scope)
        with self._get_connection() as conn:
            table_name = self._ensure_index_schema(conn, spec)
            quoted_table = _quote_identifier(table_name)
            for doc_id in ids:
                doc_key = _doc_key(scope, doc_id)
                conn.execute(
                    f"""
                    DELETE FROM {quoted_table}
                    WHERE doc_key = ? AND user_id = ? AND organization_id = ?
                    """,
                    (doc_key, int(scope.user_id), organization_id),
                )
                conn.execute(
                    """
                    DELETE FROM vector_payloads
                    WHERE id = ? AND tenant_id = ? AND app_id = ? AND index_name = ?
                      AND user_id = ? AND organization_id = ?
                    """,
                    (
                        doc_id,
                        spec.tenant_id,
                        spec.app_id,
                        spec.name,
                        int(scope.user_id),
                        organization_id,
                    ),
                )
            return len(ids)

    def _payload_rows_for_scope(
        self, conn: sqlite3.Connection, scope: UserScope, spec: IndexSpec
    ) -> list[sqlite3.Row]:
        self._ensure_metadata_schema(conn)
        return list(
            conn.execute(
                """
                SELECT id, metadata
                FROM vector_payloads
                WHERE tenant_id = ? AND app_id = ? AND index_name = ?
                  AND user_id = ? AND organization_id = ?
                """,
                (
                    spec.tenant_id,
                    spec.app_id,
                    spec.name,
                    int(scope.user_id),
                    _scope_organization_id(scope),
                ),
            )
        )

    async def delete_by_filter(
        self, scope: UserScope, spec: IndexSpec, flt: Filter
    ) -> int:
        with self._get_connection() as conn:
            self._ensure_index_schema(conn, spec)
            ids = []
            for row in self._payload_rows_for_scope(conn, scope, spec):
                metadata = json.loads(str(row["metadata"] or "{}"))
                if _filter_matches(metadata, flt):
                    ids.append(str(row["id"]))
        return await self.delete_ids(scope, spec, ids)

    async def query(self, scope: UserScope, spec: IndexSpec, q: Query) -> list[Match]:
        organization_id = _scope_organization_id(scope)
        with self._get_connection() as conn:
            table_name = self._ensure_index_schema(conn, spec)
            quoted_table = _quote_identifier(table_name)
            k = int(q.top_k)
            if q.filter is not None:
                k = max(
                    k,
                    int(
                        conn.execute(
                            """
                            SELECT COUNT(*)
                            FROM vector_payloads
                            WHERE tenant_id = ? AND app_id = ? AND index_name = ?
                              AND user_id = ? AND organization_id = ?
                            """,
                            (
                                spec.tenant_id,
                                spec.app_id,
                                spec.name,
                                int(scope.user_id),
                                organization_id,
                            ),
                        ).fetchone()[0]
                    ),
                )
            rows = conn.execute(
                f"""
                SELECT doc_id, embedding, distance, metadata
                FROM {quoted_table}
                WHERE embedding MATCH ?
                  AND k = ?
                  AND user_id = ?
                  AND organization_id = ?
                """,
                (_serialize_vector(q.vector), k, int(scope.user_id), organization_id),
            ).fetchall()
            matches: list[Match] = []
            for row in rows:
                metadata = json.loads(str(row["metadata"] or "{}"))
                if not _filter_matches(metadata, q.filter):
                    continue
                matches.append(
                    Match(
                        id=str(row["doc_id"]),
                        score=_score_from_distance(spec.metric, float(row["distance"])),
                        metadata=metadata if q.include_metadata else None,
                        vector=(
                            _deserialize_vector(row["embedding"])
                            if q.include_vectors
                            else None
                        ),
                    )
                )
                if len(matches) >= q.top_k:
                    break
            return matches

    async def rebuild(self, spec: IndexSpec) -> None:
        with self._get_connection() as conn:
            self._ensure_index_schema(conn, spec)
