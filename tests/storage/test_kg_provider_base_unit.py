from __future__ import annotations

import asyncio

from democrai.core.infrastructure.storage.kg.providers.base import KGEdge, KGEvidence, KGNode, KGStorageProvider


class _BasePassProvider(KGStorageProvider):
    async def add_node(self, node: KGNode) -> None:
        await super().add_node(node)

    async def get_node(self, user_id: int, node_id: str, organization_id=None):
        await super().get_node(user_id, node_id, organization_id)
        return None

    async def update_node(self, user_id: int, node_id: str, properties, organization_id=None, **kwargs):
        await super().update_node(user_id, node_id, properties, organization_id, **kwargs)

    async def delete_node(self, user_id: int, node_id: str, soft: bool = True, organization_id=None):
        await super().delete_node(user_id, node_id, soft, organization_id)

    async def add_edge(self, edge: KGEdge) -> None:
        await super().add_edge(edge)

    async def get_edge(self, user_id: int, edge_id: str, organization_id=None):
        await super().get_edge(user_id, edge_id, organization_id)
        return None

    async def update_edge(self, user_id: int, edge_id: str, properties, organization_id=None, **kwargs):
        await super().update_edge(user_id, edge_id, properties, organization_id, **kwargs)

    async def delete_edge(self, user_id: int, edge_id: str, soft: bool = True, organization_id=None):
        await super().delete_edge(user_id, edge_id, soft, organization_id)

    async def add_evidence(self, evidence: KGEvidence) -> None:
        await super().add_evidence(evidence)

    async def delete_evidence(self, user_id: int, evidence_id: str, organization_id=None) -> None:
        await super().delete_evidence(user_id, evidence_id, organization_id)

    async def link_edge_to_evidence(self, user_id: int, edge_id: str, evidence_id: str, organization_id=None) -> None:
        await super().link_edge_to_evidence(user_id, edge_id, evidence_id, organization_id)

    async def get_neighbors(self, user_id: int, node_id: str, edge_type=None, limit: int = 10, organization_id=None):
        await super().get_neighbors(user_id, node_id, edge_type, limit, organization_id)
        return []

    async def traversal(self, user_id: int, start_node_id: str, max_depth: int = 2, organization_id=None):
        await super().traversal(user_id, start_node_id, max_depth, organization_id)
        return []

    async def prune_orphan_nodes(self, user_id: int, node_ids: list[str], organization_id=None):
        await super().prune_orphan_nodes(user_id, node_ids, organization_id)
        return 0

    def run_migrations(self) -> None:
        super().run_migrations()


def test_kg_storage_provider_abstract_default_bodies():
    p = _BasePassProvider()
    node = KGNode(id="n1", type="T", user_id=1)
    edge = KGEdge(id="e1", src="n1", dst="n2", type="REL", user_id=1)
    ev = KGEvidence(id="k1", kind="text", ref="r1", user_id=1)

    asyncio.run(p.add_node(node))
    assert asyncio.run(p.get_node(1, "n1")) is None
    asyncio.run(p.update_node(1, "n1", {"x": 1}))
    asyncio.run(p.delete_node(1, "n1"))
    asyncio.run(p.add_edge(edge))
    assert asyncio.run(p.get_edge(1, "e1")) is None
    asyncio.run(p.update_edge(1, "e1", {"x": 1}))
    asyncio.run(p.delete_edge(1, "e1"))
    asyncio.run(p.add_evidence(ev))
    asyncio.run(p.delete_evidence(1, "k1"))
    asyncio.run(p.link_edge_to_evidence(1, "e1", "k1"))
    assert asyncio.run(p.get_neighbors(1, "n1")) == []
    assert asyncio.run(p.traversal(1, "n1")) == []
    assert asyncio.run(p.prune_orphan_nodes(1, ["n1"])) == 0
    assert p.run_migrations() is None
