from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import re
import tempfile
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


class GLiNERGLiRELEngine(BaseEngine, KGProvider):
    engine_id = "gliner_glirel"

    @classmethod
    def _missing_module_labels(cls) -> list[str]:
        checks = [
            ("gliner", "gliner"),
            ("glirel", "glirel"),
            ("loguru", "loguru"),
            ("seqeval.metrics.v1", "seqeval"),
            ("transformers", "transformers"),
        ]
        missing: list[str] = []
        for module_name, label in checks:
            try:
                module_missing = importlib.util.find_spec(module_name) is None
            except ModuleNotFoundError:
                module_missing = True
            if module_missing:
                missing.append(label)
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
            [
                "gliner",
                "glirel",
                "loguru",
                "seqeval>=1.2.2",
                "transformers",
                "huggingface-hub>=0.34,<1.0",
                "fsspec<=2025.10.0,>=2023.1.0",
                "safetensors",
            ],
            modules=["gliner", "glirel", "loguru", "seqeval.metrics.v1", "transformers"],
            force=force,
            extra_index_url=torch_plan.index_url,
            extra_pip_args=["--constraint", torch_constraint],
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_module_labels(),
            ok_message="GLiNER + GLiREL engine ready",
            error_message="GLiNER + GLiREL engine requires shared state or local dependencies",
        )

    @classmethod
    def _validate_config(
        cls, *, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"ready": True, "missing_config": [], "message": ""}

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)
        gliner = ensure_import("gliner", dependency_key="gliner")
        glirel = ensure_import("glirel", dependency_key="glirel")
        transformers = ensure_import("transformers", dependency_key="transformers")
        self._AutoTokenizer = getattr(transformers, "AutoTokenizer", None)
        self._prepared_dirs: list[tempfile.TemporaryDirectory[str]] = []
        (
            entity_model_ref,
            relation_model_ref,
            entity_backbone_ref,
            relation_backbone_ref,
        ) = self._model_refs(config)
        if not entity_model_ref:
            raise RuntimeError("gliner_entity_model_required")
        if not relation_model_ref:
            raise RuntimeError("glirel_relation_model_required")
        entity_model_ref = self._prepared_model_ref(
            entity_model_ref,
            entity_backbone_ref,
            config_filename="gliner_config.json",
        )
        relation_model_ref = self._prepared_model_ref(
            relation_model_ref,
            relation_backbone_ref,
            config_filename="glirel_config.json",
        )
        self.entity_tokenizer = (
            self._AutoTokenizer.from_pretrained(entity_backbone_ref or entity_model_ref)
            if self._AutoTokenizer is not None
            else None
        )
        self.relation_tokenizer = (
            self._AutoTokenizer.from_pretrained(relation_backbone_ref or relation_model_ref)
            if self._AutoTokenizer is not None
            else None
        )
        self.entity_model = gliner.GLiNER.from_pretrained(entity_model_ref)
        self.relation_model = glirel.GLiREL.from_pretrained(relation_model_ref)

    @staticmethod
    def _model_refs(config: dict[str, Any]) -> tuple[str, str, str, str]:
        model_path = Path(str(config.get("model_path") or "").strip())
        if str(model_path) and model_path.exists():
            entity_path = model_path / "gliner"
            relation_path = model_path / "glirel"
            entity_backbone_path = model_path / "gliner_backbone"
            relation_backbone_path = model_path / "glirel_backbone"
            return (
                str(entity_path if entity_path.exists() else model_path),
                str(relation_path if relation_path.exists() else model_path),
                str(entity_backbone_path) if entity_backbone_path.exists() else "",
                str(relation_backbone_path) if relation_backbone_path.exists() else "",
            )
        return (
            str(config.get("entity_model") or "").strip(),
            str(config.get("relation_model") or "").strip(),
            str(config.get("entity_backbone_path") or "").strip(),
            str(config.get("relation_backbone_path") or "").strip(),
        )

    def _prepared_model_ref(
        self,
        model_ref: str,
        backbone_ref: str,
        *,
        config_filename: str,
    ) -> str:
        model_path = Path(str(model_ref or "").strip())
        backbone_path = Path(str(backbone_ref or "").strip())
        if not model_path.exists() or not backbone_path.exists():
            return model_ref
        config_path = model_path / config_filename
        if not config_path.exists():
            return model_ref
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or not str(config.get("model_name") or "").strip():
            return model_ref
        prepared = tempfile.TemporaryDirectory(prefix="democrai-gliner-glirel-")
        self._prepared_dirs.append(prepared)
        prepared_path = Path(prepared.name)
        for child in model_path.iterdir():
            target = prepared_path / child.name
            if child.name == config_filename:
                continue
            target.symlink_to(child, target_is_directory=child.is_dir())
        backbone_config = backbone_path / "config.json"
        if backbone_config.exists() and not (prepared_path / "config.json").exists():
            (prepared_path / "config.json").symlink_to(backbone_config)
        config["model_name"] = str(backbone_path)
        (prepared_path / config_filename).write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(prepared_path)

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
        return await asyncio.to_thread(
            self._extract_triples_sync,
            content,
            options,
        )

    def _extract_triples_sync(
        self,
        content: str,
        options: KGExtractionOptions,
    ) -> ExtractedKnowledgeGraph:
        entity_labels = self._labels(options.entity_labels, "entity_labels")
        relation_labels = self._labels(options.relation_labels, "relation_labels")
        threshold = self._threshold(options)
        entities = self.entity_model.predict_entities(
            content,
            entity_labels,
            threshold=threshold,
        )
        tokens = self._tokens(content)
        ner = self._ner_payload(entities, tokens, max_entities=options.max_entities)
        if not ner:
            return ExtractedKnowledgeGraph()
        relations = self._predict_windowed_relations(
            tokens=tokens,
            ner=ner,
            relation_labels=relation_labels,
            threshold=threshold,
            top_k=self._top_k(options),
            options=options,
        )
        graph = ExtractedKnowledgeGraph(
            entities=self._graph_entities(ner),
            relations=self._graph_relations(relations, max_relations=options.max_relations),
        )
        if current_ai_call_context() is None:
            return graph
        prompt_tokens = self._entity_token_count(content) + self._relation_token_count(
            tokens=tokens,
            options=options,
        )
        return EngineMethodResponse(
            result=graph,
            usage=EngineUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=prompt_tokens,
            ),
            metadata={
                "usage_source": "tokenizer",
                "usage_calculation": "engines.gliner_glirel.engine.GLiNERGLiRELEngine._extract_triples_sync",
            },
        )

    def _labels(self, option_labels: list[str], config_key: str) -> list[str]:
        raw = option_labels or list(self.config.get(config_key) or [])
        labels = [str(item or "").strip() for item in raw if str(item or "").strip()]
        if not labels:
            raise RuntimeError(f"gliner_glirel_{config_key}_required")
        return labels

    def _threshold(self, options: KGExtractionOptions) -> float:
        value = (
            options.threshold
            if options.threshold is not None
            else self.config.get("threshold")
        )
        return float(value if value is not None else 0.5)

    def _top_k(self, options: KGExtractionOptions) -> int:
        value = options.top_k if options.top_k is not None else self.config.get("top_k")
        return max(1, int(value if value is not None else 1))

    def _max_relation_tokens(self, options: KGExtractionOptions) -> int:
        value = self._option_extra(options, "max_relation_tokens")
        if value in (None, ""):
            value = self.config.get("max_relation_tokens")
        return max(1, int(value if value is not None else 360))

    def _relation_window_overlap(self, options: KGExtractionOptions) -> int:
        value = self._option_extra(options, "relation_window_overlap")
        if value in (None, ""):
            value = self.config.get("relation_window_overlap")
        return max(0, int(value if value is not None else 48))

    @staticmethod
    def _option_extra(options: KGExtractionOptions, name: str) -> Any:
        extra = options.extra if isinstance(options.extra, dict) else {}
        return extra.get(name)

    def _predict_windowed_relations(
        self,
        *,
        tokens: list[dict[str, Any]],
        ner: list[list[Any]],
        relation_labels: list[str],
        threshold: float,
        top_k: int,
        options: KGExtractionOptions,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for start, end in self._relation_windows(len(tokens), options):
            window_ner = self._window_ner_payload(ner, start=start, end=end)
            if not window_ner:
                continue
            relations = self.relation_model.predict_relations(
                [token["text"] for token in tokens[start:end]],
                relation_labels,
                threshold=threshold,
                ner=window_ner,
                top_k=top_k,
            )
            for relation in relations:
                source = self._relation_text(
                    relation.get("head_text") or relation.get("source_text")
                )
                target = self._relation_text(
                    relation.get("tail_text") or relation.get("target_text")
                )
                relation_type = str(
                    relation.get("label") or relation.get("relation") or ""
                ).strip()
                key = (source.casefold(), relation_type.casefold(), target.casefold())
                if not source or not target or not relation_type or key in seen:
                    continue
                seen.add(key)
                rows.append(relation)
                if len(rows) >= max(1, int(options.max_relations or 1)):
                    return rows
        return rows

    def _relation_windows(
        self,
        token_count: int,
        options: KGExtractionOptions,
    ) -> list[tuple[int, int]]:
        size = self._max_relation_tokens(options)
        overlap = min(self._relation_window_overlap(options), max(0, size - 1))
        if token_count <= size:
            return [(0, token_count)]
        windows: list[tuple[int, int]] = []
        start = 0
        step = max(1, size - overlap)
        while start < token_count:
            end = min(token_count, start + size)
            windows.append((start, end))
            if end >= token_count:
                break
            start += step
        return windows

    def _entity_token_count(self, text: str) -> int:
        if self.entity_tokenizer is None:
            return 0
        encoded = self.entity_tokenizer(
            str(text or ""),
            add_special_tokens=True,
            return_attention_mask=True,
        )
        attention_mask = encoded.get("attention_mask")
        if isinstance(attention_mask, list):
            return int(sum(int(value or 0) for value in attention_mask))
        input_ids = encoded.get("input_ids")
        if isinstance(input_ids, list):
            return int(len(input_ids))
        return 0

    def _relation_token_count(
        self,
        *,
        tokens: list[dict[str, Any]],
        options: KGExtractionOptions,
    ) -> int:
        if self.relation_tokenizer is None:
            return 0
        total = 0
        for start, end in self._relation_windows(len(tokens), options):
            window_text = " ".join(str(token["text"]) for token in tokens[start:end]).strip()
            if not window_text:
                continue
            encoded = self.relation_tokenizer(
                window_text,
                add_special_tokens=True,
                return_attention_mask=True,
            )
            attention_mask = encoded.get("attention_mask")
            if isinstance(attention_mask, list):
                total += int(sum(int(value or 0) for value in attention_mask))
                continue
            input_ids = encoded.get("input_ids")
            if isinstance(input_ids, list):
                total += int(len(input_ids))
        return total

    @staticmethod
    def _window_ner_payload(
        ner: list[list[Any]],
        *,
        start: int,
        end: int,
    ) -> list[list[Any]]:
        rows: list[list[Any]] = []
        for row in ner:
            entity_start = int(row[0])
            entity_end = int(row[1])
            if entity_start < start or entity_end >= end:
                continue
            rows.append([entity_start - start, entity_end - start, row[2], row[3]])
        return rows

    @staticmethod
    def _tokens(text: str) -> list[dict[str, Any]]:
        return [
            {"text": match.group(0), "start": match.start(), "end": match.end()}
            for match in re.finditer(r"\S+", text)
        ]

    @staticmethod
    def _entity_text(entity: dict[str, Any]) -> str:
        return str(entity.get("text") or entity.get("entity") or "").strip()

    @classmethod
    def _entity_span(
        cls,
        entity: dict[str, Any],
        tokens: list[dict[str, Any]],
    ) -> tuple[int, int] | None:
        start = entity.get("start")
        end = entity.get("end")
        if isinstance(start, int) and isinstance(end, int):
            token_indexes = [
                index
                for index, token in enumerate(tokens)
                if int(token["end"]) > start and int(token["start"]) < end
            ]
            if token_indexes:
                return min(token_indexes), max(token_indexes) + 1
        text = cls._entity_text(entity)
        if not text:
            return None
        entity_tokens = [item.group(0) for item in re.finditer(r"\S+", text)]
        if not entity_tokens:
            return None
        token_texts = [str(token["text"]) for token in tokens]
        size = len(entity_tokens)
        for index in range(0, max(0, len(token_texts) - size + 1)):
            if token_texts[index : index + size] == entity_tokens:
                return index, index + size
        return None

    @classmethod
    def _ner_payload(
        cls,
        entities: list[dict[str, Any]],
        tokens: list[dict[str, Any]],
        *,
        max_entities: int,
    ) -> list[list[Any]]:
        rows: list[list[Any]] = []
        seen: set[tuple[str, str]] = set()
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            text = cls._entity_text(entity)
            label = str(entity.get("label") or entity.get("type") or "Entity").strip()
            span = cls._entity_span(entity, tokens)
            if not text or span is None:
                continue
            key = (text.casefold(), label.casefold())
            if key in seen:
                continue
            seen.add(key)
            rows.append([span[0], span[1] - 1, label or "Entity", text])
            if len(rows) >= max(1, int(max_entities or 1)):
                break
        return rows

    @staticmethod
    def _graph_entities(ner: list[list[Any]]) -> list[KGEntity]:
        return [
            KGEntity(name=str(row[3]), entity_type=str(row[2]))
            for row in ner
        ]

    @staticmethod
    def _relation_text(value: Any) -> str:
        if isinstance(value, list):
            return " ".join(str(item) for item in value).strip()
        return str(value or "").strip()

    @classmethod
    def _graph_relations(
        cls,
        relations: list[dict[str, Any]],
        *,
        max_relations: int,
    ) -> list[KGRelation]:
        rows: list[KGRelation] = []
        seen: set[tuple[str, str, str]] = set()
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            source = cls._relation_text(
                relation.get("head_text") or relation.get("source_text")
            )
            target = cls._relation_text(
                relation.get("tail_text") or relation.get("target_text")
            )
            relation_type = str(relation.get("label") or relation.get("relation") or "").strip()
            if not source or not target or not relation_type or source == target:
                continue
            key = (source.casefold(), relation_type.casefold(), target.casefold())
            if key in seen:
                continue
            seen.add(key)
            score = relation.get("score")
            rows.append(
                KGRelation(
                    relation_type=relation_type,
                    source_entity_name=source,
                    target_entity_name=target,
                    confidence=float(score) if isinstance(score, (int, float)) else None,
                )
            )
            if len(rows) >= max(1, int(max_relations or 1)):
                break
        return rows
