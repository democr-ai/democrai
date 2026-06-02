from __future__ import annotations

from modules.system.utils.actions.engine import models as models_mod


def test_system_engine_model_helpers_sanitize_and_parse():
    assert models_mod.sanitize_name(" acme/tiny model.gguf ") == "acme_tiny_model.gguf"
    assert models_mod.sanitize_name("///") == "model"
    assert models_mod.parse_capabilities("chat, vision\nchat") == ["chat"]
    assert models_mod.parse_capabilities(["embed", "", "embed", "rerank"]) == [
        "embedding",
        "reranking",
    ]
