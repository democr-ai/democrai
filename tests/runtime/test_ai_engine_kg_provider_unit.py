from __future__ import annotations

import asyncio

import pytest

from democrai.core.application.ai.constants import methods_for_capabilities
from democrai.core.application.ai.engine.base.kg import KGProvider
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.application.ai.engine.schemas.kg import ExtractedKnowledgeGraph
from democrai.core.application.ai.engine.schemas.kg import KGEntity
from democrai.core.application.ai.engine.schemas.kg import KGExtractionOptions
from democrai.core.application.ai.engine.schemas.kg import KGRelation


class _Provider(KGProvider):
    async def _extract_triples(
        self,
        *,
        kind: str,
        title: str | None,
        summary: str | None,
        content: str,
        options: KGExtractionOptions,
    ) -> ExtractedKnowledgeGraph:
        return ExtractedKnowledgeGraph(
            entities=[
                KGEntity(
                    name=title or content,
                    entity_type=kind,
                    confidence=float(options.max_entities),
                )
            ],
            relations=[],
        )


def test_triples_capability_maps_to_runtime_method():
    assert methods_for_capabilities(["triples_extractor"]) == ["extract_triples"]
    assert methods_for_capabilities(["kg"]) == ["extract_triples"]


def test_kg_provider_contract_normalizes_options():
    provider = _Provider({"model": "kg-model"})

    result = asyncio.run(
        provider.extract_triples(
            kind="chunk",
            title="Alice",
            content="Alice works at Acme.",
            options={"max_entities": 2},
        )
    )

    assert result.entities[0].name == "Alice"
    assert result.entities[0].entity_type == "chunk"
    assert result.entities[0].confidence == 2.0


def test_kg_schema_serialization_round_trip():
    graph = ExtractedKnowledgeGraph(
        entities=[KGEntity(name="Alice", entity_type="Person")],
        relations=[
            KGRelation(
                relation_type="WORKS_AT",
                source_entity_name="Alice",
                target_entity_name="Acme",
            )
        ],
    )

    restored = python_value(json_value(graph))

    assert isinstance(restored, ExtractedKnowledgeGraph)
    assert restored.entities[0].name == "Alice"
    assert restored.relations[0].relation_type == "WORKS_AT"


def test_worker_payload_rebuilds_kg_options():
    worker_mod = __import__(
        "democrai.core.application.ai.engine.worker",
        fromlist=["_method_payload"],
    )

    payload = worker_mod._method_payload(
        "extract_triples",
        {
            "kind": "chunk",
            "content": "Alice works at Acme.",
            "options": {"max_entities": 3},
        },
    )

    assert isinstance(payload["options"], KGExtractionOptions)
    assert payload["options"].max_entities == 3


@pytest.mark.asyncio
async def test_runtime_provider_dispatches_extract_triples(monkeypatch):
    provider_mod = __import__(
        "democrai.core.application.ai.engine.runtime.provider",
        fromlist=["EngineRuntimeProvider"],
    )
    calls = []

    async def _invoke_with_usage(provider, method, payload, **_kwargs):
        calls.append((provider.engine_row_id, method, payload))
        return ExtractedKnowledgeGraph(
            entities=[KGEntity(name="Alice", entity_type="Person")],
            relations=[],
        )

    monkeypatch.setattr(provider_mod, "invoke_with_usage", _invoke_with_usage)
    provider = provider_mod.EngineRuntimeProvider(
        engine_row_id=7,
        model_registry_id=8,
        engine_id="kg",
        config={"model": "m"},
    )

    result = await provider.extract_triples(
        kind="chunk",
        title=None,
        summary=None,
        content="Alice works at Acme.",
        options={"max_entities": 1},
    )

    assert result.entities[0].name == "Alice"
    assert calls == [
        (
            7,
            "extract_triples",
            {
                "kind": "chunk",
                "title": None,
                "summary": None,
                "content": "Alice works at Acme.",
                "options": {"max_entities": 1},
            },
        )
    ]
