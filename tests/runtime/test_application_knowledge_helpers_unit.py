from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from democrai.core.application.knowledge.models import KnowledgeIngestItem, KnowledgeSourceInput


def test_metadata_enrich_and_inference_helpers():
    mod = __import__("democrai.core.application.knowledge.service_helper.metadata", fromlist=["dummy"])

    source = KnowledgeSourceInput(source_type="chat", mime_type="")
    item = KnowledgeIngestItem(kind="document_chunk", content="Meeting on 2025-03-09 14:30", title="Report")
    enriched = mod.enrich_ingest_item(source=source, item=item)

    assert enriched.metadata["source_type"] == "chat"
    assert enriched.metadata["source_kind"] == "chat"
    assert enriched.metadata["item_scope"] == "raw"
    assert enriched.metadata["retrieval_tier"] == 3
    assert enriched.metadata["time_year"] == 2025
    assert enriched.metadata["time_month"] == 3
    assert enriched.metadata["time_day"] == 9
    assert enriched.metadata["time_hour"] == 14
    assert enriched.metadata["time_minute"] == 30

    assert mod.infer_source_kind(source_type="agent", mime_type=None, item_kind=None) == "agent"
    assert mod.infer_source_kind(source_type="x", mime_type="image/png", item_kind=None) == "image"
    assert mod.infer_source_kind(source_type="x", mime_type="audio/wav", item_kind=None) == "audio"
    assert mod.infer_source_kind(source_type="x", mime_type="video/mp4", item_kind=None) == "video"
    assert mod.infer_source_kind(source_type="document", mime_type=None, item_kind=None) == "document"

    assert mod.infer_item_scope(item_kind="table_summary") == "summary"
    assert mod.infer_item_scope(item_kind="abc_chunk") == "chunk"
    assert mod.infer_item_scope(item_kind="voice_transcript") == "transcript"
    assert mod.infer_item_scope(item_kind="doc_index") == "index"
    assert mod.infer_item_scope(item_kind="chat_turn") == "message"
    assert mod.infer_item_scope(item_kind="other") == "raw"

    assert mod.infer_retrieval_tier(item_scope="summary") == 1
    assert mod.infer_retrieval_tier(item_scope="unknown") == 3


def test_metadata_temporal_parsers_and_payload_builders():
    mod = __import__("democrai.core.application.knowledge.service_helper.metadata", fromlist=["dummy"])

    slash = mod.extract_temporal_metadata(
        title="", summary="", content="evento il 03/04/2024 09:45", metadata={}
    )
    assert slash["time_iso"] == "2024-04-03T09:45"

    ym = mod.extract_temporal_metadata(
        title="", summary="", content="rilascio 2024-11", metadata={}
    )
    assert ym["time_iso"] == "2024-11"

    y = mod.extract_temporal_metadata(
        title="", summary="", content="anno 2023", metadata={}
    )
    assert y["time_iso"] == "2023"

    existing = mod.extract_temporal_metadata(
        title="", summary="", content="", metadata={"time_year": 2020, "time_month": 2}
    )
    assert existing["time_granularity"] == "month"

    payload = mod.build_time_node_payload({"time_year": 2021, "time_month": 7})
    assert payload["time_iso"] == "2021-07"
    assert payload["node_id"] == "time:2021-07"
    assert mod.build_time_node_payload({}) == {}
    assert mod.build_time_node_payload({"time_iso": ""}) == {}

    assert mod._infer_granularity({"time_hour": 1}) == "hour"
    assert mod._infer_granularity({"time_day": 1}) == "day"
    assert mod._infer_granularity({"time_month": 1}) == "month"
    assert mod._infer_granularity({}) == "year"


def test_embedding_hash_provider_and_run_sync():
    mod = __import__("democrai.core.application.knowledge.embedding", fromlist=["dummy"])

    with pytest.raises(ValueError):
        mod.HashEmbeddingProvider(dim=0)

    provider = mod.HashEmbeddingProvider(dim=8)
    vectors = provider.embed_texts(["Hello World", "Hello World", ""])
    assert len(vectors) == 3
    assert len(vectors[0]) == 8
    assert vectors[0] == vectors[1]
    assert vectors[2] == [0.0] * 8

    assert mod._run_sync(asyncio.sleep(0, result=3)) == 3

    async def _inside_loop():
        return mod._run_sync(asyncio.sleep(0, result=4))

    assert asyncio.run(_inside_loop()) == 4


def test_embedding_model_registry_provider_paths(monkeypatch):
    mod = __import__("democrai.core.application.knowledge.embedding", fromlist=["dummy"])

    with pytest.raises(ValueError):
        mod.ModelRegistryEmbeddingProvider(
            model_registry_id=0,
            dim=3,
            model_id="embedding",
        )
    with pytest.raises(ValueError):
        mod.ModelRegistryEmbeddingProvider(
            model_registry_id=4,
            dim=0,
            model_id="embedding",
        )

    provider = mod.ModelRegistryEmbeddingProvider(
        model_registry_id=4,
        dim=3,
        model_id="embedding",
    )
    assert provider.embed_texts([]) == []

    calls = []

    class _P:
        async def embed_texts(self, texts):
            return [[1.0, 2.0, 3.0] for _ in texts]

    async def _provider_by_id(model_registry_id):
        calls.append(model_registry_id)
        return {"status": "ok", "provider": _P()}

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_by_model_registry_id=_provider_by_id,
            )
        ),
    )
    vectors = provider.embed_texts(["a", "b"])
    assert vectors == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
    assert calls == [4]

    class _BadP:
        async def embed_texts(self, texts):
            return [[1.0, 2.0] for _ in texts]

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_by_model_registry_id=lambda *_a, **_k: asyncio.sleep(
                    0, result={"status": "ok", "provider": _BadP()}
                )
            )
        ),
    )
    with pytest.raises(ValueError):
        provider.embed_texts(["a"])

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_by_model_registry_id=lambda *_a, **_k: asyncio.sleep(
                    0, result={"status": "error", "error": "x"}
                )
            )
        ),
    )
    with pytest.raises(RuntimeError):
        provider.embed_texts(["a"])


def test_triples_base_helpers():
    mod = __import__("democrai.core.application.knowledge.triples_helper._base", fromlist=["dummy"])

    assert mod.clamp_limit(0, fallback=5) == 5
    assert mod.clamp_limit(3, fallback=5) == 3

    payload = {
        "entities": [
            {"name": "Alice", "entity_type": "Person", "confidence": 0.8, "metadata": {"k": 1}},
            {"name": "alice", "entity_type": "Person"},
            {"name": "Acme", "entity_type": "Organization"},
            "bad",
            {},
        ],
        "relations": [
            {
                "relation_type": "WORKS_AT",
                "source_entity_name": "Alice",
                "target_entity_name": "Acme",
                "confidence": 0.7,
                "weight": 0.6,
                "metadata": {"s": 1},
            },
            {
                "relation_type": "WORKS_AT",
                "source_entity_name": "Alice",
                "target_entity_name": "Acme",
            },
            {
                "relation_type": "SELF",
                "source_entity_name": "Alice",
                "target_entity_name": "Alice",
            },
            "bad",
        ],
    }
    graph = mod.normalize_graph_payload(payload, max_entities=2, max_relations=2)
    assert len(graph.entities) == 2
    assert len(graph.relations) == 1

    assert "kind: doc" in mod.build_llm_prompt(kind="doc", title="t", summary="s", content="c")
    assert mod.normalize_graph_payload(None, max_entities=1, max_relations=1).entities == ()


def test_triples_wrappers_and_heuristic():
    wrappers = __import__("democrai.core.application.knowledge.triples_helper._wrappers", fromlist=["dummy"])
    heuristic_mod = __import__("democrai.core.application.knowledge.triples_helper._heuristic", fromlist=["dummy"])
    base = __import__("democrai.core.application.knowledge.triples_helper._base", fromlist=["dummy"])

    class _Extractor(base.TripleExtractor):
        def extract_item(self, *, kind, title, summary, content):
            return base.ExtractedKnowledgeGraph(
                entities=(
                    __import__("democrai.core.application.knowledge.models", fromlist=["dummy"]).EntityInput(name="Alice", entity_type="Person"),
                ),
                relations=(),
            )

    cond = wrappers.ConditionalTripleExtractor(_Extractor(), allowed_kinds=("doc",), min_chars=3, max_chars=5)
    assert cond.extract_item(kind="other", title=None, summary=None, content="abcdef").entities == ()
    assert cond.extract_item(kind="doc", title=None, summary=None, content="ab").entities == ()
    assert cond.extract_item(kind="doc", title=None, summary=None, content="abcdef").entities

    class _Fail(base.TripleExtractor):
        def extract_item(self, **_k):
            raise RuntimeError("x")

    comp = wrappers.CompositeTripleExtractor(_Extractor(), _Fail(), max_entities=1, max_relations=1)
    out = comp.extract_item(kind="doc", title=None, summary=None, content="abc")
    assert len(out.entities) == 1

    h = heuristic_mod.HeuristicTripleExtractor(max_entities=5, max_relations=5)
    empty = h.extract_item(kind="doc", title="", summary="", content="")
    assert empty.entities == () and empty.relations == ()

    text = "Dr Alice works at Acme Inc. Alice partners with Globex Group."
    graph = h.extract_item(kind="doc", title="Title", summary=None, content=text)
    assert graph.entities
    assert graph.relations
    assert heuristic_mod.HeuristicTripleExtractor._infer_entity_type("Dr Alice") == "Person"
    assert heuristic_mod.HeuristicTripleExtractor._infer_entity_type("Acme Inc") == "Organization"
    assert heuristic_mod.HeuristicTripleExtractor._clean_entity_name("  Alice, ") == "Alice"
    assert heuristic_mod.HeuristicTripleExtractor._sentences("A. B\nC")


def test_triples_heuristic_remaining_branches():
    heuristic_mod = __import__("democrai.core.application.knowledge.triples_helper._heuristic", fromlist=["dummy"])

    h = heuristic_mod.HeuristicTripleExtractor(max_entities=1, max_relations=5)
    # same source/target should be ignored by relation extraction
    graph = h.extract_item(
        kind="doc",
        title=None,
        summary=None,
        content="Alice works at Alice.",
    )
    assert graph.relations == ()

    # _extract_entities skip stopword + short token + break at max_entities
    entities = list(h._extract_entities("The. A. Alice Bob Charlie"))
    assert len(entities) == 1

    # force branch-level coverage for stopword/single-letter guards
    class _Match:
        def __init__(self, value):
            self._value = value

        def group(self, _idx):
            return self._value

    class _RE:
        @staticmethod
        def finditer(_sentence):
            return iter([_Match("The"), _Match("A"), _Match("Alice")])

    old_re = heuristic_mod._ENTITY_RE
    heuristic_mod._ENTITY_RE = _RE()
    try:
        entities_forced = list(h._extract_entities("ignored"))
    finally:
        heuristic_mod._ENTITY_RE = old_re
    assert entities_forced and entities_forced[0].name == "Alice"

    # _infer_entity_type fallback branches
    assert heuristic_mod.HeuristicTripleExtractor._infer_entity_type("Alice Cooper") == "Person"
    assert heuristic_mod.HeuristicTripleExtractor._infer_entity_type("AcmeGroup") == "Organization"


@pytest.mark.asyncio
async def test_projection_vector_and_graph_remaining_branches():
    projection_vector = __import__(
        "democrai.core.application.knowledge.service_helper.projection_vector", fromlist=["dummy"]
    )
    graph_mod = __import__(
        "democrai.core.application.knowledge.service_helper.graph", fromlist=["dummy"]
    )

    class _Repo:
        def __init__(self, item):
            self.item = item
            self.status_calls = []

        def get_item(self, _item_id):
            return self.item

        def set_item_embedding(self, **_kw):
            return self.item

        def mark_item_status(self, **kw):
            self.status_calls.append(kw)

        def upsert_projection_state(self, **_kw):
            return None

    class _VectorStore:
        async def ensure_index(self, _spec):
            return None

        async def upsert(self, _scope, _spec, _docs):
            return None

        async def delete_ids(self, _scope, _spec, _ids):
            return None

        async def info(self):
            return SimpleNamespace(name="vs")

    base_item = SimpleNamespace(
        id="i1",
        source_id="s1",
        user_id=1,
        organization_id=None,
        owner_access_level=3,
        is_public=False,
        kind="document_chunk",
        embedding_vector_json=None,
        embedding_text="hello",
        embedding_dim=3,
        version=1,
        deleted_at=None,
    )
    service = SimpleNamespace(
        repository=_Repo(base_item),
        _module_name_for_source_id=lambda _sid: "demo",
        _vector_spec_for_module=lambda _m: SimpleNamespace(dim=4, tenant_id="t", app_id="a", name="idx"),
        embedding_provider=SimpleNamespace(
            embed_texts=lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts],
            model_id="m",
            model_version="1",
        ),
        vector_store=_VectorStore(),
        _projection_scopes_for_item=lambda **_kw: [(1, None)],
        kg_store=SimpleNamespace(
            get_node=lambda *_a, **_k: None,
            add_node=lambda *_a, **_k: None,
            update_node=lambda *_a, **_k: None,
        ),
    )

    # deleted item early-return
    deleted = SimpleNamespace(**{**base_item.__dict__, "deleted_at": "x"})
    service.repository.item = deleted
    await projection_vector.process_vector_job(service, SimpleNamespace(payload={"item_id": "i1"}))
    assert service.repository.status_calls == []

    # vector dim mismatch branch
    service.repository.item = SimpleNamespace(**{**base_item.__dict__, "embedding_dim": 99, "deleted_at": None})
    with pytest.raises(ValueError):
        await projection_vector.process_vector_job(
            service, SimpleNamespace(payload={"item_id": "i1"})
        )

    # delete job with missing item early-return
    service.repository.item = None
    await projection_vector.process_vector_delete_job(
        service, SimpleNamespace(payload={"item_id": "i1"})
    )

    # graph.refresh_item_graph with missing item
    service_graph = SimpleNamespace(
        repository=SimpleNamespace(
            list_entities=lambda _id: ["e"],
            list_relations=lambda _id: ["r"],
            get_item=lambda _id: None,
            replace_item_graph=lambda **_kw: None,
        ),
        triple_extractor=object(),
        _merge_graph_inputs=lambda **_kw: ((), ()),
    )
    entities, relations = graph_mod.refresh_item_graph(
        service_graph, item_id="i1", user_id=1, organization_id=None
    )
    assert entities == ["e"] and relations == ["r"]

    # merge_graph_inputs relation skip branch (missing source entity)
    item = SimpleNamespace(kind="k", title="t", summary="s", content="c")
    entities_in = [SimpleNamespace(id="e1", canonical_name="Alice", entity_type="Person", confidence=0.8, metadata_json={})]
    relations_in = [SimpleNamespace(source_entity_id="missing", target_entity_id="e1", relation_type="X", confidence=1.0, weight=1.0, metadata_json={})]
    merged_e, merged_r = graph_mod.merge_graph_inputs(
        SimpleNamespace(
            _entity_key=lambda n: n.casefold(),
            _relation_key=lambda r: (r.relation_type, r.source_entity_name, r.target_entity_name),
            _metadata_load=lambda m: m or {},
            triple_extractor=SimpleNamespace(extract_item=lambda **_kw: SimpleNamespace(entities=(), relations=())),
        ),
        item=item,
        entities=entities_in,
        relations=relations_in,
    )
    assert merged_e and merged_r == ()

    # node id fallback and scope fallback branch
    assert graph_mod.graph_entity_node_id(SimpleNamespace(canonical_name="", entity_type="")) .startswith("entity:")
    scope = graph_mod.graph_scope_for_item(
        SimpleNamespace(_projection_scopes_for_item=lambda **_kw: [(2, None)]),
        requester_user_id=1,
        requester_organization_id=None,
        requester_access_level=3,
        owner_user_id=9,
        owner_organization_id=None,
        owner_access_level=3,
        is_public=False,
        kind="document_chunk",
    )
    assert scope == (9, None)

    # dedupe-continue path
    scopes = graph_mod.projection_scopes_for_item(
        service=SimpleNamespace(),
        owner_user_id=1,
        owner_organization_id=None,
        owner_access_level=3,
        is_public=False,
        kind="document_chunk",
    )
    assert (1, None) in scopes


def test_triples_model_registry_extractor(monkeypatch):
    mod = __import__("democrai.core.application.knowledge.triples_helper._llm", fromlist=["dummy"])
    base = __import__("democrai.core.application.knowledge.triples_helper._base", fromlist=["dummy"])
    runtime_schemas = __import__(
        "democrai.core.application.ai.engine.schemas.runtime",
        fromlist=["dummy"],
    )
    kg_schemas = __import__(
        "democrai.core.application.ai.engine.schemas.kg",
        fromlist=["dummy"],
    )

    with pytest.raises(ValueError):
        mod.ModelRegistryTripleExtractor(model_registry_id=0)

    extractor = mod.ModelRegistryTripleExtractor(
        model_registry_id=6,
        max_entities=2,
        max_relations=3,
        max_tokens=1,
    )
    assert extractor.max_tokens >= 64
    assert extractor.extract_item(kind="doc", title=None, summary=None, content="   ").entities == ()
    assert extractor.model_registry_id == 6

    class _Provider:
        async def generate_completion(self, messages, options):
            assert messages and options.max_tokens >= 64
            return SimpleNamespace(content=json.dumps({
                "entities": [{"name": "Alice", "entity_type": "Person"}],
                "relations": [],
            }))

    calls = []

    async def _provider_by_id(model_registry_id):
        calls.append(model_registry_id)
        return {"status": "ok", "provider": _Provider()}

    monkeypatch.setattr(
        mod,
        "get_provider_definition",
        lambda _provider_id: {"runtime_methods": ["generate_completion"]},
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_by_model_registry_id=_provider_by_id,
                get_model_by_registry_id=lambda _model_registry_id: SimpleNamespace(
                    id=6,
                    capabilities=["chat"],
                    engine=SimpleNamespace(provider="p"),
                ),
            )
        ),
    )
    out = extractor.extract_item(kind="doc", title="t", summary="s", content="c")
    assert len(out.entities) == 1
    assert calls == [6]

    class _KGProvider:
        async def extract_triples(self, **kwargs):
            assert kwargs["options"].max_tokens >= 64
            return runtime_schemas.EngineMethodResponse(
                result=kg_schemas.ExtractedKnowledgeGraph(
                    entities=[
                        kg_schemas.KGEntity(name="Acme", entity_type="Organization")
                    ],
                    relations=[],
                )
            )

    monkeypatch.setattr(
        mod,
        "get_provider_definition",
        lambda _provider_id: {"runtime_methods": ["extract_triples"]},
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_by_model_registry_id=lambda *_a, **_k: asyncio.sleep(
                    0, result={"status": "ok", "provider": _KGProvider()}
                ),
                get_model_by_registry_id=lambda _model_registry_id: SimpleNamespace(
                    id=6,
                    capabilities=["triples_extractor"],
                    engine=SimpleNamespace(provider="p"),
                ),
            )
        ),
    )
    out = extractor.extract_item(kind="doc", title="t", summary="s", content="c")
    assert len(out.entities) == 1
    assert out.entities[0].name == "Acme"

    class _ProviderEmpty:
        async def generate_completion(self, messages, options):
            return SimpleNamespace(content="")

    monkeypatch.setattr(
        mod,
        "get_provider_definition",
        lambda _provider_id: {"runtime_methods": ["generate_completion"]},
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_by_model_registry_id=lambda *_a, **_k: asyncio.sleep(
                    0, result={"status": "ok", "provider": _ProviderEmpty()}
                ),
                get_model_by_registry_id=lambda _model_registry_id: SimpleNamespace(
                    id=6,
                    capabilities=["chat"],
                    engine=SimpleNamespace(provider="p"),
                ),
            )
        ),
    )
    assert extractor.extract_item(kind="doc", title="t", summary="s", content="c").entities == ()

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_by_model_registry_id=lambda *_a, **_k: asyncio.sleep(
                    0, result={"status": "error"}
                ),
                get_model_by_registry_id=lambda _model_registry_id: SimpleNamespace(
                    id=6,
                    capabilities=["chat"],
                    engine=SimpleNamespace(provider="p"),
                ),
            )
        ),
    )
    with pytest.raises(RuntimeError):
        extractor.extract_item(kind="doc", title="t", summary="s", content="c")

    # _run_sync running loop branch
    async def _inside_loop():
        return mod._run_sync(asyncio.sleep(0, result=9))

    assert asyncio.run(_inside_loop()) == 9

    # keep base symbol used
    assert isinstance(base.GRAPH_SYSTEM_PROMPT, str)
