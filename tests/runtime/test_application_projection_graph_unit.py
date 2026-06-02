from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Repo:
    def __init__(self, item=None, source=None, entities=None, relations=None, source_items=None):
        self.item = item
        self.source = source
        self.entities = list(entities or [])
        self.relations = list(relations or [])
        self.source_items = list(source_items or [])
        self.status_calls = []
        self.state_calls = []

    def get_item(self, _item_id):
        return self.item

    def get_source(self, _source_id):
        return self.source

    def list_items_for_source(self, **_k):
        return list(self.source_items)

    def mark_item_status(self, **kw):
        self.status_calls.append(kw)

    def upsert_projection_state(self, **kw):
        self.state_calls.append(kw)

    def list_entities(self, _item_id):
        return list(self.entities)

    def list_relations(self, _item_id):
        return list(self.relations)


class _KG:
    def __init__(self):
        self.edges = {}
        self.added_edges = []
        self.updated_edges = []
        self.deleted_edges = []
        self.deleted_nodes = []
        self.linked = []
        self.evidence_added = []

    async def link_edge_to_evidence(self, user_id, edge_id, evidence_id, organization_id=None):
        self.linked.append((user_id, edge_id, evidence_id, organization_id))

    async def delete_edge(self, user_id, edge_id, soft=True, organization_id=None):
        self.deleted_edges.append((user_id, edge_id, organization_id, soft))

    async def delete_node(self, user_id, node_id, soft=True, organization_id=None):
        self.deleted_nodes.append((user_id, node_id, organization_id, soft))

    async def get_edge(self, user_id, edge_id, organization_id=None):
        return self.edges.get((user_id, edge_id, organization_id))

    async def add_edge(self, edge):
        self.added_edges.append(edge)
        self.edges[(edge.user_id, edge.id, edge.organization_id)] = edge

    async def update_edge(self, user_id, edge_id, properties, organization_id=None, **kwargs):
        self.updated_edges.append((user_id, edge_id, properties, organization_id, kwargs))

    async def add_evidence(self, evidence):
        self.evidence_added.append(evidence)


class _Svc:
    def __init__(self, repo):
        self.repository = repo
        self.kg_store = _KG()
        self.nodes = []
        self.edges = []

    def _metadata_load(self, payload):
        if isinstance(payload, dict):
            return payload
        return payload or {}

    def _projection_scopes_for_item(self, **_k):
        return [(1, None)]

    def _refresh_item_graph(self, **_k):
        return self.repository.entities, self.repository.relations

    def _graph_entity_node_id(self, entity):
        return f"entity:{entity.id}"

    async def _upsert_node(self, node):
        self.nodes.append(node)

    async def _upsert_edge(self, edge):
        self.edges.append(edge)

    async def _ensure_evidence(self, evidence):
        await self.kg_store.add_evidence(evidence)


@pytest.mark.asyncio
async def test_projection_graph_process_job_happy_path(monkeypatch):
    mod = __import__("democrai.core.application.knowledge.service_helper.projection_graph", fromlist=["dummy"])

    item = SimpleNamespace(
        id="i1",
        source_id="s1",
        user_id=1,
        organization_id=None,
        deleted_at=None,
        owner_access_level=3,
        is_public=False,
        kind="document_chunk",
        title="Item",
        content="Body",
        summary="Summary",
        metadata_json={"event": "Launch", "time_year": 2024},
        external_ref=None,
        version=2,
    )
    source = SimpleNamespace(
        id="s1",
        title="Source",
        external_ref=None,
        source_type="document",
        mime_type="text/plain",
        media_uri=None,
        metadata_json={"k": 1},
    )
    e1 = SimpleNamespace(id="e1", entity_type="Person", canonical_name="Alice", metadata_json={"role": "Engineer", "event": "Launch"}, confidence=0.8)
    e2 = SimpleNamespace(id="e2", entity_type="Organization", canonical_name="Acme", metadata_json={}, confidence=0.7)
    r1 = SimpleNamespace(id="r1", relation_type="WORKS_AT", source_entity_id="e1", target_entity_id="e2", confidence=0.9, weight=0.5, metadata_json={"k": "v"})
    r_bad = SimpleNamespace(id="rb", relation_type="BAD", source_entity_id="missing", target_entity_id="e2", confidence=None, weight=None, metadata_json={})

    repo = _Repo(item=item, source=source, entities=[e1, e2], relations=[r1, r_bad], source_items=[item])
    svc = _Svc(repo)

    monkeypatch.setattr(mod, "build_hierarchy_edges", lambda **_k: [SimpleNamespace(src_item_id="i1", dst_item_id="i1", edge_type="PARENT_OF")])
    monkeypatch.setattr(mod, "build_time_node_payload", lambda _m: {"node_id": "time:2024", "time_iso": "2024", "time_year": 2024})

    await mod.process_kg_job(svc, SimpleNamespace(payload={"item_id": "i1", "source_id": "s1"}))

    assert repo.status_calls and repo.status_calls[-1]["kg_status"] == "synced"
    assert repo.state_calls and repo.state_calls[-1]["status"] == "synced"
    assert svc.nodes  # source/item/entity/attribute/event/time nodes
    assert any(edge.type == "DERIVED_FROM" for edge in svc.edges)
    assert any(edge.type == "PARTICIPATES_IN" for edge in svc.edges)
    assert any(edge.type == "HAS_ATTRIBUTE" for edge in svc.edges)
    assert any(edge.type == "WORKS_AT" for edge in svc.edges)


@pytest.mark.asyncio
async def test_projection_graph_process_job_early_returns(monkeypatch):
    mod = __import__("democrai.core.application.knowledge.service_helper.projection_graph", fromlist=["dummy"])

    svc_missing = _Svc(_Repo(item=None, source=None))
    await mod.process_kg_job(svc_missing, SimpleNamespace(payload={"item_id": "x", "source_id": "y"}))
    assert not svc_missing.nodes and not svc_missing.edges

    deleted_item = SimpleNamespace(id="i", source_id="s", deleted_at="x")
    svc_deleted = _Svc(_Repo(item=deleted_item, source=SimpleNamespace(id="s")))
    await mod.process_kg_job(svc_deleted, SimpleNamespace(payload={"item_id": "i", "source_id": "s"}))
    assert not svc_deleted.nodes and not svc_deleted.edges


@pytest.mark.asyncio
async def test_projection_graph_delete_job_and_helpers(monkeypatch):
    mod = __import__("democrai.core.application.knowledge.service_helper.projection_graph", fromlist=["dummy"])

    item = SimpleNamespace(
        id="i1",
        source_id="s1",
        user_id=1,
        organization_id=None,
        owner_access_level=3,
        is_public=False,
        kind="document_chunk",
        metadata_json={"time_year": 2024},
        version=1,
    )
    source = SimpleNamespace(id="s1")
    e1 = SimpleNamespace(id="e1", metadata_json={"role": "Engineer", "events": ["Kickoff"]})
    rel = SimpleNamespace(id="r1")
    repo = _Repo(item=item, source=source, entities=[e1], relations=[rel], source_items=[item])
    svc = _Svc(repo)

    monkeypatch.setattr(mod, "build_hierarchy_edges", lambda **_k: [SimpleNamespace(src_item_id="i1", dst_item_id="i2", edge_type="PARENT_OF")])
    monkeypatch.setattr(mod, "build_time_node_payload", lambda _m: {"node_id": "time:2024"})

    await mod.process_kg_delete_job(svc, SimpleNamespace(payload={"item_id": "i1", "source_id": "s1"}))

    assert repo.status_calls[-1]["kg_status"] == "deleted"
    assert repo.state_calls[-1]["status"] == "deleted"
    assert svc.kg_store.deleted_edges
    assert svc.kg_store.deleted_nodes

    # helper pure functions
    assert mod._value_iterable(None) == []
    assert mod._value_iterable("x") == ["x"]
    assert mod._value_iterable(["x", "", None]) == ["x"]
    assert mod._attribute_node_id("n1", "k", "v").startswith("attribute:")
    assert mod._event_node_id("n1", "v").startswith("event:")


@pytest.mark.asyncio
async def test_projection_graph_upsert_edge_and_ensure_evidence():
    mod = __import__("democrai.core.application.knowledge.service_helper.projection_graph", fromlist=["dummy"])
    svc = _Svc(_Repo())

    edge = SimpleNamespace(id="e1", src="a", dst="b", type="REL", user_id=1, organization_id=None, properties={"x": 1}, weight=0.5, confidence=0.8, source="s", evidence_id="ev")

    await mod.upsert_edge(svc, edge)
    assert svc.kg_store.added_edges

    await mod.upsert_edge(svc, edge)
    assert svc.kg_store.updated_edges

    evidence = SimpleNamespace(id="ev")
    await mod.ensure_evidence(svc, evidence)
    assert svc.kg_store.evidence_added

    async def _dup(_evidence):
        raise RuntimeError("duplicate key")

    svc.kg_store.add_evidence = _dup
    with pytest.raises(RuntimeError, match="duplicate key"):
        await mod.ensure_evidence(svc, evidence)

    async def _fail(_evidence):
        raise RuntimeError("boom")

    svc.kg_store.add_evidence = _fail
    with pytest.raises(RuntimeError):
        await mod.ensure_evidence(svc, evidence)
