from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_rebel_catalog_is_visible(monkeypatch):
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

    rows = catalog_mod.list_engine_models("rebel")

    assert rows
    assert rows[0]["id"] == "babelscape-rebel-large"
    assert rows[0]["artifacts"][0]["format"] == "hf_snapshot"
    assert rows[0]["artifacts"][0]["target"] == "rebel"
    assert rows[0]["capabilities"] == ["triples_extractor"]
    assert rows[0]["metadata"]["usage"] == "non-commercial"


def test_rebel_install_uses_torch_and_packages(monkeypatch):
    engine_mod = __import__("engines.rebel.engine", fromlist=["REBELEngine"])
    calls = []

    monkeypatch.setattr(
        engine_mod,
        "install_torch_runtime",
        lambda force=False: SimpleNamespace(index_url="https://torch.example/simple"),
    )
    monkeypatch.setattr(
        engine_mod,
        "write_installed_torch_constraint",
        lambda: "/tmp/constraints.txt",
    )
    monkeypatch.setattr(
        engine_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)),
    )

    engine_mod.REBELEngine._install(force=True)

    assert calls
    packages, kwargs = calls[0]
    assert "transformers" in packages
    assert kwargs["modules"] == ["transformers"]
    assert kwargs["extra_pip_args"] == ["--constraint", "/tmp/constraints.txt"]


def test_rebel_parse_triplets():
    engine_mod = __import__("engines.rebel.engine", fromlist=["REBELEngine"])

    triplets = engine_mod.REBELEngine._parse_triplets(
        "<s> <triplet> Alice <subj> Acme <obj> works at </s>"
    )

    assert triplets == [{"head": "Alice", "type": "works at", "tail": "Acme"}]


def test_rebel_uses_materialized_model_path(monkeypatch, tmp_path):
    engine_mod = __import__("engines.rebel.engine", fromlist=["REBELEngine"])
    refs = []
    (tmp_path / "rebel").mkdir()

    monkeypatch.setattr(
        engine_mod,
        "ensure_import",
        lambda module, dependency_key=None: SimpleNamespace(
            AutoTokenizer=SimpleNamespace(
                from_pretrained=lambda ref: refs.append(("tokenizer", ref)) or object()
            ),
            AutoModelForSeq2SeqLM=SimpleNamespace(
                from_pretrained=lambda ref: refs.append(("model", ref)) or object()
            ),
        ),
    )

    engine_mod.REBELEngine({"model_path": str(tmp_path)})

    assert refs == [
        ("tokenizer", str(tmp_path / "rebel")),
        ("model", str(tmp_path / "rebel")),
    ]


def test_rebel_extracts_graph(monkeypatch):
    engine_mod = __import__("engines.rebel.engine", fromlist=["REBELEngine"])

    class _Tensor:
        def to(self, _device):
            return self

    class _Tokenizer:
        def __call__(self, text, **kwargs):
            assert text == "Alice works at Acme."
            assert kwargs["max_length"] == 64
            return {"input_ids": _Tensor(), "attention_mask": _Tensor()}

        def batch_decode(self, generated, skip_special_tokens=False):
            assert generated == ["generated"]
            assert skip_special_tokens is False
            return ["<s> <triplet> Alice <subj> Acme <obj> works at </s>"]

    class _Model:
        device = "cpu"

        def generate(self, input_ids, attention_mask=None, **kwargs):
            assert kwargs["max_length"] == 64
            assert kwargs["num_beams"] == 2
            return ["generated"]

    monkeypatch.setattr(
        engine_mod,
        "ensure_import",
        lambda module, dependency_key=None: SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda _ref: _Tokenizer()),
            AutoModelForSeq2SeqLM=SimpleNamespace(from_pretrained=lambda _ref: _Model()),
        ),
    )

    engine = engine_mod.REBELEngine(
        {
            "model": "Babelscape/rebel-large",
            "max_length": 64,
            "num_beams": 2,
            "num_return_sequences": 1,
            "length_penalty": 0,
        }
    )
    result = asyncio.run(
        engine.extract_triples(kind="chunk", content="Alice works at Acme.")
    )

    assert [entity.name for entity in result.entities] == ["Alice", "Acme"]
    assert result.relations[0].source_entity_name == "Alice"
    assert result.relations[0].relation_type == "works at"
    assert result.relations[0].target_entity_name == "Acme"
