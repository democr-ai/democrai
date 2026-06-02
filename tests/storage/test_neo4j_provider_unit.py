from __future__ import annotations

import asyncio
import importlib
import sys
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.storage.kg.providers.base import KGEdge, KGEvidence, KGNode
import democrai.core.infrastructure.storage.kg.providers.neo4j as neo4j_mod
from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.infrastructure.storage.kg.providers.neo4j import (
    Neo4jKGStorage,
    _identity_pattern,
    _optional_scope_clause,
    _sanitize_graph_name,
)


class _FakeResult:
    def __init__(self, single_value=None, data_value=None):
        self._single_value = single_value
        self._data_value = data_value or []

    async def single(self):
        return self._single_value

    async def data(self):
        return self._data_value


class _FakeSession:
    def __init__(self, single_value=None, data_value=None, sink=None):
        self._single_value = single_value
        self._data_value = data_value or []
        self._sink = sink if sink is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def run(self, query, **params):
        self._sink.append((query, params))
        return _FakeResult(self._single_value, self._data_value)


class _FakeDriver:
    def __init__(self, single_value=None, data_value=None):
        self.calls = []
        self.single_value = single_value
        self.data_value = data_value or []
        self.closed = False

    def session(self):
        return _FakeSession(self.single_value, self.data_value, self.calls)

    async def close(self):
        self.closed = True


class _SyncResult:
    def __init__(self, sink):
        self._sink = sink

    def consume(self):
        self._sink.append("consumed")


class _SyncSession:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def run(self, statement):
        self._sink.append(statement)
        return _SyncResult(self._sink)


class _SyncDriver:
    def __init__(self):
        self.calls = []
        self.closed = False

    def session(self):
        return _SyncSession(self.calls)

    def close(self):
        self.closed = True


def test_neo4j_provider_helper_functions():
    assert _sanitize_graph_name("12 bad-type", fallback="X") == "_12_bad_type"
    assert _sanitize_graph_name("", fallback="Fallback") == "Fallback"
    assert _optional_scope_clause("n", None) == " AND n.organization_id = $organization_id"
    assert _optional_scope_clause("n", 10) == " AND n.organization_id = $organization_id"
    assert _identity_pattern("src", True).endswith(
        "AND src.organization_id = $src_organization_id"
    )
    assert _identity_pattern("src", False).endswith(
        "AND src.organization_id = $src_organization_id"
    )


def test_neo4j_provider_init_and_missing_dependency(monkeypatch):
    monkeypatch.setattr(neo4j_mod, "HAS_NEO4J", False)
    with pytest.raises(ProviderNotAvailableError):
        Neo4jKGStorage("bolt://db", "neo4j", "pw")

    created = []
    driver = _FakeDriver()
    monkeypatch.setattr(neo4j_mod, "HAS_NEO4J", True)
    monkeypatch.setattr(
        neo4j_mod,
        "AsyncGraphDatabase",
        SimpleNamespace(
            driver=lambda uri, auth=None: created.append((uri, auth)) or driver
        ),
        raising=False,
    )

    provider = Neo4jKGStorage("bolt://db", "neo4j", "pw")
    assert created == [("bolt://db", ("neo4j", "pw"))]
    assert provider.driver is driver


def test_neo4j_module_import_branch_when_dependency_exists(monkeypatch):
    fake_neo4j = SimpleNamespace(AsyncGraphDatabase=SimpleNamespace(), GraphDatabase=SimpleNamespace())
    monkeypatch.setitem(sys.modules, "neo4j", fake_neo4j)
    reloaded = importlib.reload(neo4j_mod)
    assert reloaded.HAS_NEO4J is True


def test_neo4j_provider_run_migrations_and_close(monkeypatch):
    sync_driver = _SyncDriver()
    provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    provider._uri = "bolt://db"
    provider._auth = ("neo4j", "pw")
    provider.driver = _FakeDriver()

    monkeypatch.setattr(
        neo4j_mod,
        "GraphDatabase",
        SimpleNamespace(driver=lambda uri, auth=None: sync_driver),
        raising=False,
    )

    provider.run_migrations()
    asyncio.run(provider.close())

    assert any("DROP CONSTRAINT kg_node_identity" in call for call in sync_driver.calls)
    assert any("DROP CONSTRAINT kg_evidence_identity" in call for call in sync_driver.calls)
    assert any("CREATE CONSTRAINT kg_node_identity" in call for call in sync_driver.calls)
    assert any("CREATE INDEX kg_edge_scope" in call for call in sync_driver.calls)
    assert sync_driver.closed is True
    assert provider.driver.closed is True


def test_neo4j_provider_writes_scope_fields_on_create():
    driver = _FakeDriver()
    provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    provider.driver = driver

    node = KGNode(
        id="node-1",
        type="Person",
        user_id=1,
        organization_id=10,
        properties={"custom": "Alice", "organization_id": 99, "id": "bad"},
    )
    edge = KGEdge(
        id="edge-1",
        src="node-1",
        dst="node-2",
        type="WORKS_AT",
        user_id=1,
        organization_id=10,
        properties={"custom": "import", "source": "reserved"},
    )
    evidence = KGEvidence(
        id="ev-1",
        kind="doc",
        ref="doc-1",
        user_id=1,
        organization_id=10,
        payload={"page": 3},
    )

    asyncio.run(provider.add_node(node))
    asyncio.run(provider.add_edge(edge))
    asyncio.run(provider.add_evidence(evidence))

    node_query, node_params = driver.calls[0]
    edge_query, edge_params = driver.calls[1]
    evidence_query, evidence_params = driver.calls[2]

    assert "organization_id: $organization_id" in node_query
    assert node_params["organization_id"] == 10
    assert node_params["props"] == {"custom": "Alice"}
    assert "organization_id: $organization_id" in edge_query
    assert edge_params["src_organization_id"] == 10
    assert edge_params["dst_organization_id"] == 10
    assert edge_params["organization_id"] == 10
    assert edge_params["props"] == {"custom": "import"}
    assert "organization_id: $organization_id" in evidence_query
    assert evidence_params["organization_id"] == 10


def test_neo4j_provider_add_node_without_org_scope():
    driver = _FakeDriver()
    provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    provider.driver = driver

    asyncio.run(provider.add_node(KGNode(id="node-1", type="bad label", user_id="u1")))

    query, params = driver.calls[0]
    assert ":bad_label" in query
    assert "organization_id: $organization_id" in query
    assert params["organization_id"] == 0


def test_neo4j_provider_reads_and_traverses_with_optional_org_scope():
    record = {
        "n": {
            "id": "node-1",
            "user_id": 1,
            "organization_id": 10,
            "type": "Person",
            "name": "Alice",
            "created_at": 1,
            "updated_at": 2,
        },
        "labels": ["KGNode", "Person"],
    }
    driver = _FakeDriver(single_value=record, data_value=[{"node_id": "node-2", "depth": 1}])
    provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    provider.driver = driver

    node = asyncio.run(provider.get_node(1, "node-1", organization_id=10))
    walk = asyncio.run(provider.traversal(1, "node-1", max_depth=3, organization_id=10))

    assert node is not None
    assert node.organization_id == 10
    assert walk == [{"node_id": "node-2", "depth": 1}]
    get_query, get_params = driver.calls[0]
    traversal_query, traversal_params = driver.calls[1]
    assert "n.organization_id = $organization_id" in get_query
    assert get_params["organization_id"] == 10
    assert "start.organization_id = $organization_id" in traversal_query
    assert "size(rels)" in traversal_query
    assert traversal_params["organization_id"] == 10


def test_neo4j_provider_getters_updates_and_deletes_cover_edge_paths():
    edge_record = {
        "r": {
            "id": "edge-1",
            "user_id": 1,
            "organization_id": 10,
            "type": "WORKS_AT",
            "weight": 0.9,
            "confidence": 0.8,
            "evidence_id": "ev-1",
            "source": "import",
            "created_at": 1,
            "updated_at": 2,
            "extra": "x",
        },
        "src_id": "src",
        "dst_id": "dst",
    }
    driver = _FakeDriver(single_value=edge_record)
    provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    provider.driver = driver
    missing_provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    missing_provider.driver = _FakeDriver(single_value=None)

    edge = asyncio.run(provider.get_edge(1, "edge-1", organization_id=10))
    missing = asyncio.run(missing_provider.get_node("u1", "missing"))
    asyncio.run(
        provider.update_node(
            1,
            "node-1",
            {"p": 1, "organization_id": 99},
            organization_id=10,
            name="Alice",
            external_ref="ext-1",
            deleted_at=9,
            ignored="nope",
        )
    )
    asyncio.run(provider.delete_node(1, "node-1", soft=True, organization_id=10))
    asyncio.run(provider.delete_node(1, "node-1", soft=False))
    asyncio.run(
        provider.update_edge(
            1,
            "edge-1",
            {"p": 1, "source": "reserved"},
            organization_id=10,
            weight=0.5,
            confidence=0.4,
            source="manual",
            evidence_id="ev-2",
            deleted_at=7,
            ignored="nope",
        )
    )
    asyncio.run(provider.delete_edge(1, "edge-1", soft=True, organization_id=10))
    asyncio.run(provider.delete_edge(1, "edge-1", soft=False))

    assert edge is not None
    assert edge.organization_id == 10
    assert edge.properties == {"extra": "x"}
    assert missing is None
    assert "n.name = $name" in driver.calls[1][0]
    assert driver.calls[1][1]["props"] == {"p": 1}
    assert "n.external_ref = $external_ref" in driver.calls[1][0]
    assert "n.deleted_at = $deleted_at" in driver.calls[1][0]
    assert "DETACH DELETE n" in driver.calls[3][0]
    assert "r.weight = $weight" in driver.calls[4][0]
    assert "r.evidence_id = $evidence_id" in driver.calls[4][0]
    assert driver.calls[4][1]["props"] == {"p": 1}
    assert "DELETE r" in driver.calls[6][0]


def test_neo4j_provider_hard_deletes_evidence_and_prunes_orphans():
    driver = _FakeDriver(single_value={"deleted_count": 2})
    provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    provider.driver = driver

    asyncio.run(provider.delete_evidence(1, "ev-1", organization_id=10))
    pruned = asyncio.run(
        provider.prune_orphan_nodes(1, ["n1", "n2", "n1"], organization_id=10)
    )

    assert "DETACH DELETE e" in driver.calls[0][0]
    assert driver.calls[0][1]["id"] == "ev-1"
    assert "n.id IN $ids" in driver.calls[1][0]
    assert "DETACH DELETE node" in driver.calls[1][0]
    assert driver.calls[1][1]["ids"] == ["n1", "n2"]
    assert pruned == 2


def test_neo4j_provider_neighbors_link_and_traversal_without_org():
    driver = _FakeDriver(
        single_value=None,
        data_value=[{"edge_id": "e1", "edge_type": "WORKS_AT", "node_id": "dst"}],
    )
    provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    provider.driver = driver

    asyncio.run(provider.link_edge_to_evidence("u1", "e1", "ev-1"))
    neighbors = asyncio.run(
        provider.get_neighbors("u1", "src", edge_type="works at", limit=5)
    )
    walk = asyncio.run(provider.traversal("u1", "src", max_depth=0))

    assert neighbors == [{"edge_id": "e1", "edge_type": "WORKS_AT", "node_id": "dst"}]
    assert walk == [{"edge_id": "e1", "edge_type": "WORKS_AT", "node_id": "dst"}]
    assert "WHEN $ev_id IN coalesce(r.evidence_ids, [])" in driver.calls[0][0]
    assert driver.calls[0][1]["organization_id"] == 0
    assert ":works_at" in driver.calls[1][0]
    assert "LIMIT $limit" in driver.calls[1][0]
    assert driver.calls[1][1]["organization_id"] == 0
    assert "*1..1" in driver.calls[2][0]
    assert driver.calls[2][1]["organization_id"] == 0


def test_neo4j_provider_get_edge_none_and_neighbors_without_edge_type():
    provider = Neo4jKGStorage.__new__(Neo4jKGStorage)
    provider.driver = _FakeDriver(single_value=None, data_value=[{"node_id": "dst"}])

    edge = asyncio.run(provider.get_edge("u1", "missing"))
    neighbors = asyncio.run(provider.get_neighbors("u1", "src"))

    assert edge is None
    assert neighbors == [{"node_id": "dst"}]
    assert ":KG_REL:" not in provider.driver.calls[1][0]
    assert provider.driver.calls[0][1]["organization_id"] == 0
    assert provider.driver.calls[1][1]["organization_id"] == 0
