from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_gliner_glirel_catalog_is_visible(monkeypatch):
    manifests_mod = __import__(
        "democrai.core.application.ai.engine.manifests",
        fromlist=["get_engine_roots"],
    )
    catalog_mod = __import__(
        "democrai.core.application.ai.models.catalog",
        fromlist=["list_engine_models"],
    )
    manifests_mod.list_engine_manifests.cache_clear()
    monkeypatch.setattr(manifests_mod, "get_engine_roots", lambda: (Path("engines").resolve(),))
    monkeypatch.setattr(catalog_mod, "get_engine_roots", lambda: (Path("engines").resolve(),))

    rows = catalog_mod.list_engine_models("gliner_glirel")

    assert rows
    assert rows[0]["artifacts"][0]["format"] == "hf_snapshot"
    assert [artifact["target"] for artifact in rows[0]["artifacts"]] == [
        "gliner",
        "gliner_backbone",
        "glirel",
        "glirel_backbone",
    ]
    assert rows[0]["capabilities"] == ["triples_extractor"]
    assert rows[0]["runtime"]["defaults"]["runtime"]["entity_model"]
    assert rows[0]["runtime"]["defaults"]["runtime"]["relation_model"]


def test_gliner_glirel_install_uses_torch_and_packages(monkeypatch):
    engine_mod = __import__("engines.gliner_glirel.engine", fromlist=["GLiNERGLiRELEngine"])
    calls = []

    monkeypatch.setattr(
        engine_mod,
        "resolve_torch_runtime_plan",
        lambda **kwargs: SimpleNamespace(
            packages=("torch==2.10.0",),
            modules=("torch",),
            index_url="https://download.pytorch.org/whl/cu128",
        ),
    )
    monkeypatch.setattr(
        engine_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)),
    )

    engine_mod.GLiNERGLiRELEngine._install(force=True)

    packages, kwargs = calls[0]
    assert packages == [
        "torch==2.10.0",
        "gliner==0.2.26",
        "glirel==1.2.1",
        "loguru==0.7.3",
        "seqeval==1.2.2",
        "transformers==4.57.3",
        "huggingface-hub>=0.34,<1.0",
        "fsspec<=2025.10.0,>=2023.1.0",
        "safetensors==0.7.0",
    ]
    assert "fsspec<=2025.10.0,>=2023.1.0" in packages
    assert kwargs["modules"] == [
        "torch",
        "gliner",
        "glirel",
        "loguru",
        "seqeval",
        "seqeval.metrics.v1",
        "transformers",
        "safetensors",
    ]
    assert kwargs["force"] is True
    assert kwargs["extra_index_url"] == "https://download.pytorch.org/whl/cu128"
    assert len(calls) == 1


def test_gliner_glirel_ready_checks_declared_runtime_chain(monkeypatch):
    engine_mod = __import__("engines.gliner_glirel.engine", fromlist=["GLiNERGLiRELEngine"])

    monkeypatch.setattr(engine_mod.GLiNERGLiRELEngine, "_missing_modules", lambda *args: [])
    monkeypatch.setattr(
        engine_mod.GLiNERGLiRELEngine,
        "_missing_chain_versions",
        classmethod(lambda cls: []),
    )
    monkeypatch.setattr(
        engine_mod.GLiNERGLiRELEngine,
        "_runtime_symbols_available",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(
        engine_mod.GLiNERGLiRELEngine,
        "_default_missing_shared",
        classmethod(lambda cls: []),
    )

    result = engine_mod.GLiNERGLiRELEngine._check_ready()

    assert result["ready"] is True
    assert result["missing_local"] == []


def test_gliner_glirel_rejects_torch_below_cve_floor(monkeypatch):
    engine_mod = __import__("engines.gliner_glirel.engine", fromlist=["GLiNERGLiRELEngine"])

    monkeypatch.setattr(engine_mod, "_distribution_version_from_sys_path", lambda name: "2.5.1")

    assert engine_mod.GLiNERGLiRELEngine._torch_min_version_available() is False


def test_gliner_glirel_uses_materialized_model_path(monkeypatch, tmp_path):
    engine_mod = __import__("engines.gliner_glirel.engine", fromlist=["GLiNERGLiRELEngine"])
    entity_refs = []
    relation_refs = []
    (tmp_path / "gliner").mkdir()
    (tmp_path / "glirel").mkdir()

    monkeypatch.setattr(
        engine_mod,
        "ensure_import",
        lambda module, dependency_key=None: SimpleNamespace(
            GLiNER=SimpleNamespace(
                from_pretrained=lambda ref: entity_refs.append(ref) or object()
            ),
            GLiREL=SimpleNamespace(
                from_pretrained=lambda ref: relation_refs.append(ref) or object()
            ),
        ),
    )

    engine_mod.GLiNERGLiRELEngine({"model_path": str(tmp_path)})

    assert entity_refs == [str(tmp_path / "gliner")]
    assert relation_refs == [str(tmp_path / "glirel")]


def test_gliner_glirel_extracts_graph(monkeypatch):
    engine_mod = __import__("engines.gliner_glirel.engine", fromlist=["GLiNERGLiRELEngine"])

    class _EntityModel:
        def predict_entities(self, text, labels, threshold=0.5):
            assert labels == ["Person", "Organization"]
            assert threshold == 0.4
            return [
                {"text": "Alice", "label": "Person", "start": 0, "end": 5},
                {"text": "Acme", "label": "Organization", "start": 15, "end": 19},
            ]

    class _RelationModel:
        def predict_relations(self, tokens, labels, threshold=0.5, ner=None, top_k=1):
            assert tokens == ["Alice", "works", "at", "Acme", "."]
            assert labels == ["works at"]
            assert threshold == 0.4
            assert top_k == 1
            assert ner == [[0, 0, "Person", "Alice"], [3, 3, "Organization", "Acme"]]
            return [
                {
                    "head_text": ["Alice"],
                    "tail_text": ["Acme"],
                    "label": "works at",
                    "score": 0.91,
                }
            ]

    monkeypatch.setattr(
        engine_mod,
        "ensure_import",
        lambda module, dependency_key=None: SimpleNamespace(
            GLiNER=SimpleNamespace(from_pretrained=lambda _ref: _EntityModel()),
            GLiREL=SimpleNamespace(from_pretrained=lambda _ref: _RelationModel()),
        ),
    )

    engine = engine_mod.GLiNERGLiRELEngine(
        {
            "entity_model": "entity-model",
            "relation_model": "relation-model",
            "entity_labels": ["Person", "Organization"],
            "relation_labels": ["works at"],
            "threshold": 0.4,
            "top_k": 1,
        }
    )
    result = asyncio.run(
        engine.extract_triples(
            kind="chunk",
            content="Alice works at Acme .",
        )
    )

    assert [entity.name for entity in result.entities] == ["Alice", "Acme"]
    assert result.relations[0].source_entity_name == "Alice"
    assert result.relations[0].relation_type == "works at"
    assert result.relations[0].target_entity_name == "Acme"
    assert result.relations[0].confidence == 0.91


def test_gliner_glirel_requires_labels(monkeypatch):
    engine_mod = __import__("engines.gliner_glirel.engine", fromlist=["GLiNERGLiRELEngine"])
    monkeypatch.setattr(
        engine_mod,
        "ensure_import",
        lambda module, dependency_key=None: SimpleNamespace(
            GLiNER=SimpleNamespace(from_pretrained=lambda _ref: object()),
            GLiREL=SimpleNamespace(from_pretrained=lambda _ref: object()),
        ),
    )
    engine = engine_mod.GLiNERGLiRELEngine(
        {"entity_model": "entity-model", "relation_model": "relation-model"}
    )

    try:
        asyncio.run(engine.extract_triples(kind="chunk", content="Alice works at Acme."))
    except RuntimeError as exc:
        assert str(exc) == "gliner_glirel_entity_labels_required"
    else:
        raise AssertionError("missing entity labels did not fail")
