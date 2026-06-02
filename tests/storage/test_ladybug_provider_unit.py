from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.infrastructure.storage.kg.providers.base import KGEdge
from democrai.core.infrastructure.storage.kg.providers.base import KGEvidence
from democrai.core.infrastructure.storage.kg.providers.base import KGNode
from democrai.core.infrastructure.storage.kg.providers.ladybug import HAS_LADYBUG
from democrai.core.infrastructure.storage.kg.providers.ladybug import LadybugKGStorage
from democrai.core.infrastructure.storage.kg.providers.ladybug import (
    denormalize_organization_id,
)
from democrai.core.infrastructure.storage.kg.providers.ladybug import load_json_list
from democrai.core.infrastructure.storage.kg.providers.ladybug import load_json_object
from democrai.core.infrastructure.storage.kg.providers.ladybug import scoped_key


class FakeQueryResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def rows_as_dict(self):
        return self

    def get_all(self):
        return self.rows


class FakeAsyncConnection:
    def __init__(self, database, max_concurrent_queries=4):
        self.database = database
        self.max_concurrent_queries = max_concurrent_queries
        self.calls = []
        self.results = []

    async def execute(self, query, parameters=None):
        self.calls.append((query, parameters))
        if "RETURN" in query and self.results:
            return self.results.pop(0)
        return FakeQueryResult()


class FakeSyncConnection:
    def __init__(self, database):
        self.database = database
        self.calls = []

    def execute(self, query):
        self.calls.append(query)
        return FakeQueryResult()

    def close(self):
        return None


class FakeDatabase:
    def __init__(self, path):
        self.path = path


def fake_ladybug(sync_connections, async_connections):
    def create_sync_connection(database):
        connection = FakeSyncConnection(database)
        sync_connections.append(connection)
        return connection

    def create_async_connection(database, max_concurrent_queries=4):
        connection = FakeAsyncConnection(database, max_concurrent_queries)
        async_connections.append(connection)
        return connection

    return SimpleNamespace(
        Database=FakeDatabase,
        Connection=create_sync_connection,
        AsyncConnection=create_async_connection,
    )


def install_fake_ladybug(monkeypatch):
    sync_connections = []
    async_connections = []
    provider_module = sys.modules[LadybugKGStorage.__module__]
    monkeypatch.setattr(provider_module, "HAS_LADYBUG", True)
    monkeypatch.setattr(
        provider_module,
        "ladybug",
        fake_ladybug(sync_connections, async_connections),
    )
    return sync_connections, async_connections


def test_ladybug_provider_requires_dependency(monkeypatch):
    provider_module = sys.modules[LadybugKGStorage.__module__]
    monkeypatch.setattr(provider_module, "HAS_LADYBUG", False)
    monkeypatch.setattr(provider_module, "ladybug", None)

    with pytest.raises(ProviderNotAvailableError):
        LadybugKGStorage("kg.lbug")


def test_ladybug_helpers():
    assert scoped_key(1, None, "node") == "1:0:node"
    assert scoped_key(1, 7, "node") == "1:7:node"
    assert denormalize_organization_id(0) is None
    assert denormalize_organization_id(3) == 3
    assert load_json_object('{"a": 1}') == {"a": 1}
    assert load_json_object("[1, 2]") == {}
    assert load_json_list('["a", "b"]') == ["a", "b"]


def test_ladybug_run_migrations_creates_expected_schema(monkeypatch):
    sync_connections, async_connections = install_fake_ladybug(monkeypatch)
    store = LadybugKGStorage("kg.lbug", max_concurrent_queries=2)

    store.run_migrations()

    assert async_connections[0].database.path == "kg.lbug"
    assert async_connections[0].max_concurrent_queries == 2
    statements = "\n".join(sync_connections[0].calls)
    assert "CREATE NODE TABLE IF NOT EXISTS KGNode" in statements
    assert "CREATE NODE TABLE IF NOT EXISTS Evidence" in statements
    assert "CREATE REL TABLE IF NOT EXISTS KG_REL" in statements
    assert "FROM KGNode TO KGNode" in statements


def test_ladybug_node_crud_uses_scoped_keys(monkeypatch):
    sync_connections, async_connections = install_fake_ladybug(monkeypatch)
    store = LadybugKGStorage("kg.lbug")
    connection = async_connections[0]
    connection.results.append(
        FakeQueryResult(
            [
                {
                    "id": "n1",
                    "user_id": 1,
                    "organization_id": 2,
                    "node_type": "Person",
                    "properties_json": '{"role": "author"}',
                    "created_at": 10,
                    "updated_at": 11,
                    "deleted_at": None,
                    "name": "Alice",
                    "external_ref": "ext",
                }
            ]
        )
    )
    connection.results.append(
        FakeQueryResult(
            [
                {
                    "id": "n1",
                    "user_id": 1,
                    "organization_id": 2,
                    "node_type": "Person",
                    "properties_json": '{"role": "author"}',
                    "created_at": 10,
                    "updated_at": 11,
                    "deleted_at": None,
                    "name": "Alice",
                    "external_ref": "ext",
                }
            ]
        )
    )

    asyncio.run(
        store.add_node(
            KGNode(
                id="n1",
                type="Person",
                user_id=1,
                organization_id=2,
                properties={"role": "author"},
            )
        )
    )
    node = asyncio.run(store.get_node(1, "n1", 2))
    asyncio.run(store.update_node(1, "n1", {"city": "Rome"}, organization_id=2))
    asyncio.run(store.delete_node(1, "n1", organization_id=2))

    assert sync_connections == []
    assert node is not None
    assert node.properties == {"role": "author"}
    assert "MERGE (n:KGNode {kg_key: $kg_key})" in connection.calls[0][0]
    assert connection.calls[0][1]["kg_key"] == "1:2:n1"
    assert load_json_object(connection.calls[3][1]["properties_json"]) == {
        "role": "author",
        "city": "Rome",
    }
    assert connection.calls[4][1]["kg_key"] == "1:2:n1"


def test_ladybug_edge_evidence_neighbors_and_traversal(monkeypatch):
    install_fake_ladybug(monkeypatch)
    store = LadybugKGStorage("kg.lbug")
    connection = store.connection
    connection.results.append(
        FakeQueryResult(
            [
                {
                    "id": "e1",
                    "src_id": "n1",
                    "dst_id": "n2",
                    "user_id": 1,
                    "organization_id": 0,
                    "edge_type": "RELATED_TO",
                    "properties_json": '{"since": 2024}',
                    "created_at": 10,
                    "updated_at": 11,
                    "deleted_at": None,
                    "weight": 0.8,
                    "confidence": 0.9,
                    "evidence_id": "ev1",
                    "source": "test",
                }
            ]
        )
    )
    connection.results.append(
        FakeQueryResult(
            [
                {
                    "id": "e1",
                    "src_id": "n1",
                    "dst_id": "n2",
                    "user_id": 1,
                    "organization_id": 0,
                    "edge_type": "RELATED_TO",
                    "properties_json": '{"since": 2024}',
                    "created_at": 10,
                    "updated_at": 11,
                    "deleted_at": None,
                    "weight": 0.8,
                    "confidence": 0.9,
                    "evidence_id": "ev1",
                    "source": "test",
                }
            ]
        )
    )
    connection.results.append(FakeQueryResult([{"evidence_ids_json": '["ev1"]'}]))
    connection.results.append(
        FakeQueryResult(
            [
                {
                    "edge_id": "e1",
                    "edge_type": "RELATED_TO",
                    "node_id": "n2",
                    "node_type": "Topic",
                    "node_name": "Graphs",
                    "edge_properties": '{"since": 2024}',
                    "weight": 0.8,
                    "confidence": 0.9,
                }
            ]
        )
    )
    connection.results.append(
        FakeQueryResult(
            [
                {"node_id": "n2", "depth": 2},
                {"node_id": "n2", "depth": 1},
                {"node_id": "n3", "depth": 2},
            ]
        )
    )

    asyncio.run(
        store.add_edge(
            KGEdge(
                id="e1",
                src="n1",
                dst="n2",
                type="RELATED_TO",
                user_id=1,
                evidence_id="ev1",
            )
        )
    )
    edge = asyncio.run(store.get_edge(1, "e1"))
    asyncio.run(store.update_edge(1, "e1", {"status": "active"}))
    asyncio.run(
        store.add_evidence(
            KGEvidence(id="ev1", kind="doc", ref="doc-1", user_id=1)
        )
    )
    asyncio.run(store.link_edge_to_evidence(1, "e1", "ev2"))
    neighbors = asyncio.run(store.get_neighbors(1, "n1", edge_type="RELATED_TO"))
    traversal = asyncio.run(store.traversal(1, "n1", max_depth=2))

    assert edge is not None
    assert edge.properties == {"since": 2024}
    assert "MERGE (src)-[r:KG_REL {kg_key: $kg_key}]->(dst)" in connection.calls[0][0]
    assert connection.calls[0][1]["src_key"] == "1:0:n1"
    assert load_json_object(connection.calls[3][1]["properties_json"]) == {
        "since": 2024,
        "status": "active",
    }
    assert load_json_list(connection.calls[6][1]["evidence_ids_json"]) == ["ev1", "ev2"]
    assert neighbors[0]["edge_properties"] == {"since": 2024}
    assert traversal == [{"node_id": "n2", "depth": 1}, {"node_id": "n3", "depth": 2}]


def test_ladybug_hard_deletes_evidence_and_prunes_orphans(monkeypatch):
    install_fake_ladybug(monkeypatch)
    store = LadybugKGStorage("kg.lbug")
    connection = store.connection
    connection.results.append(FakeQueryResult([{"deleted_count": 1}]))

    asyncio.run(store.delete_evidence(1, "ev1", organization_id=2))
    pruned = asyncio.run(store.prune_orphan_nodes(1, ["n1", "n1"], organization_id=2))

    assert "DETACH DELETE e" in connection.calls[0][0]
    assert connection.calls[0][1]["kg_key"] == "1:2:ev1"
    assert "DETACH DELETE n" in connection.calls[1][0]
    assert connection.calls[1][1]["kg_key"] == "1:2:n1"
    assert pruned == 1


@pytest.mark.skipif(not HAS_LADYBUG, reason="ladybug package unavailable")
def test_ladybug_real_db_roundtrips_json_and_idempotent_records(tmp_path):
    store = LadybugKGStorage(str(tmp_path / "kg.lbug"))
    store.run_migrations()

    asyncio.run(
        store.add_node(
            KGNode(
                id="n1",
                type="Person",
                user_id=1,
                properties={"role": "author"},
            )
        )
    )
    asyncio.run(
        store.add_node(
            KGNode(
                id="n1",
                type="Person",
                user_id=1,
                properties={"role": "editor"},
            )
        )
    )
    asyncio.run(store.add_node(KGNode(id="n2", type="Person", user_id=1)))
    asyncio.run(
        store.add_edge(
            KGEdge(
                id="e1",
                src="n1",
                dst="n2",
                type="RELATED_TO",
                user_id=1,
                properties={"rank": 1},
                evidence_id="ev1",
            )
        )
    )
    asyncio.run(
        store.add_edge(
            KGEdge(
                id="e1",
                src="n1",
                dst="n2",
                type="RELATED_TO",
                user_id=1,
                properties={"rank": 2},
                evidence_id="ev1",
            )
        )
    )
    asyncio.run(store.link_edge_to_evidence(1, "e1", "ev2"))

    node = asyncio.run(store.get_node(1, "n1"))
    edge = asyncio.run(store.get_edge(1, "e1"))

    assert node is not None
    assert node.properties == {"role": "editor"}
    assert edge is not None
    assert edge.properties == {"rank": 2}
