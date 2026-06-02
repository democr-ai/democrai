from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any

from democrai.sdk.dependencies import (
    ensure_import,
    install_python_packages,
    install_torch_runtime,
    torch_runtime_matches_plan,
    write_installed_torch_constraint,
)
from democrai.sdk.engines import (
    BaseEngine,
    EngineMethodResponse,
    EngineUsage,
    ExtractedKnowledgeGraph,
    KGEntity,
    KGExtractionOptions,
    KGProvider,
    KGRelation,
    current_ai_call_context,
)


class REBELEngine(BaseEngine, KGProvider):
    engine_id = "rebel"

    @classmethod
    def _missing_module_labels(cls) -> list[str]:
        missing: list[str] = []
        if importlib.util.find_spec("transformers") is None:
            missing.append("transformers")
        try:
            torch_ready = torch_runtime_matches_plan()
        except Exception:
            torch_ready = False
        if not torch_ready:
            missing.append("PyTorch runtime")
        return missing

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        torch_plan = install_torch_runtime(force=force)
        torch_constraint = write_installed_torch_constraint()
        install_python_packages(
            ["transformers", "huggingface-hub>=0.34,<1.0", "safetensors"],
            modules=["transformers"],
            force=force,
            extra_index_url=torch_plan.index_url,
            extra_pip_args=["--constraint", torch_constraint],
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_module_labels(),
            ok_message="REBEL engine ready",
            error_message="REBEL engine requires shared state or local dependencies",
        )

    @classmethod
    def _validate_config(
        cls, *, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"ready": True, "missing_config": [], "message": ""}

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)
        transformers = ensure_import("transformers", dependency_key="transformers")
        model_ref = self._model_ref(config)
        if not model_ref:
            raise RuntimeError("rebel_model_required")
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(model_ref)
        self.model = transformers.AutoModelForSeq2SeqLM.from_pretrained(model_ref)

    @staticmethod
    def _model_ref(config: dict[str, Any]) -> str:
        model_path = Path(str(config.get("model_path") or "").strip())
        if str(model_path) and model_path.exists():
            nested = model_path / "rebel"
            if nested.exists():
                return str(nested)
            if (model_path / "config.json").exists():
                return str(model_path)
            return str(model_path)
        return str(config.get("model") or "").strip()

    async def _extract_triples(
        self,
        *,
        kind: str,
        title: str | None,
        summary: str | None,
        content: str,
        options: KGExtractionOptions,
    ) -> ExtractedKnowledgeGraph:
        if not content:
            return ExtractedKnowledgeGraph()
        return await asyncio.to_thread(self._extract_triples_sync, content, options)

    def _extract_triples_sync(
        self,
        content: str,
        options: KGExtractionOptions,
    ) -> ExtractedKnowledgeGraph:
        encoded = self.tokenizer(
            content,
            max_length=self._max_length(options),
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        generated = self.model.generate(
            encoded["input_ids"].to(self.model.device),
            attention_mask=encoded["attention_mask"].to(self.model.device),
            length_penalty=float(self.config.get("length_penalty", 0)),
            num_beams=int(self.config.get("num_beams", 3)),
            num_return_sequences=int(self.config.get("num_return_sequences", 3)),
            max_length=self._max_length(options),
        )
        decoded = self.tokenizer.batch_decode(generated, skip_special_tokens=False)
        graph = self._graph_from_decoded(decoded, max_relations=options.max_relations)
        prompt_tokens = self._attention_mask_token_count(encoded.get("attention_mask"))
        if current_ai_call_context() is None or prompt_tokens is None:
            return graph
        try:
            completion_tokens = int(generated.shape[-1]) * int(generated.shape[0])
        except Exception:
            completion_tokens = 0
        total_tokens = prompt_tokens + completion_tokens
        return EngineMethodResponse(
            result=graph,
            usage=EngineUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            ),
            metadata={
                "usage_source": "tokenizer",
                "usage_calculation": "engines.rebel.engine.REBELEngine._extract_triples_sync",
            },
        )

    @staticmethod
    def _attention_mask_token_count(value: Any) -> int | None:
        try:
            return int(value.sum().item())
        except Exception:
            return None

    def _max_length(self, options: KGExtractionOptions) -> int:
        value = options.max_tokens if options.max_tokens is not None else self.config.get("max_length")
        return max(32, int(value if value is not None else 256))

    @classmethod
    def _graph_from_decoded(
        cls,
        decoded_items: list[str],
        *,
        max_relations: int,
    ) -> ExtractedKnowledgeGraph:
        relations: list[KGRelation] = []
        entities: dict[str, KGEntity] = {}
        seen_relations: set[tuple[str, str, str]] = set()
        for item in decoded_items:
            for triple in cls._parse_triplets(str(item or "")):
                source = triple["head"]
                target = triple["tail"]
                relation_type = triple["type"]
                key = (source.casefold(), relation_type.casefold(), target.casefold())
                if key in seen_relations:
                    continue
                seen_relations.add(key)
                entities.setdefault(source.casefold(), KGEntity(name=source, entity_type="Entity"))
                entities.setdefault(target.casefold(), KGEntity(name=target, entity_type="Entity"))
                relations.append(
                    KGRelation(
                        relation_type=relation_type,
                        source_entity_name=source,
                        target_entity_name=target,
                    )
                )
                if len(relations) >= max(1, int(max_relations or 1)):
                    return ExtractedKnowledgeGraph(
                        entities=list(entities.values()),
                        relations=relations,
                    )
        return ExtractedKnowledgeGraph(
            entities=list(entities.values()),
            relations=relations,
        )

    @staticmethod
    def _parse_triplets(text: str) -> list[dict[str, str]]:
        triplets: list[dict[str, str]] = []
        relation = ""
        subject = ""
        object_ = ""
        current = ""
        for token in text.replace("<s>", "").replace("<pad>", "").replace("</s>", "").split():
            if token == "<triplet>":
                if relation and subject and object_:
                    triplets.append(
                        {"head": subject.strip(), "type": relation.strip(), "tail": object_.strip()}
                    )
                subject = ""
                relation = ""
                object_ = ""
                current = "subject"
            elif token == "<subj>":
                if relation and subject and object_:
                    triplets.append(
                        {"head": subject.strip(), "type": relation.strip(), "tail": object_.strip()}
                    )
                object_ = ""
                relation = ""
                current = "object"
            elif token == "<obj>":
                relation = ""
                current = "relation"
            elif current == "subject":
                subject = f"{subject} {token}".strip()
            elif current == "object":
                object_ = f"{object_} {token}".strip()
            elif current == "relation":
                relation = f"{relation} {token}".strip()
        if relation and subject and object_:
            triplets.append(
                {"head": subject.strip(), "type": relation.strip(), "tail": object_.strip()}
            )
        return triplets
