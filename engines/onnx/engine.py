from __future__ import annotations

import asyncio
import contextvars
import importlib.metadata
import importlib.util
from threading import Thread
from typing import Any, AsyncGenerator, List

from democrai.sdk.engines import (
    ClassificationOptions,
    ClassificationResult,
    CompletionOptions,
    CompletionResponse,
    EngineMethodResponse,
    EngineUsage,
    Message,
    MessageRole,
    RerankOptions,
    RerankResult,
    StreamChunk,
    TokenExtractionResult,
)
from democrai.sdk.engines import BaseEngine, LLMProvider
from democrai.sdk.dependencies import (
    ensure_import,
    install_python_packages,
    install_torch_runtime,
    torch_runtime_matches_plan,
    write_installed_torch_constraint,
)


class OnnxEngine(BaseEngine, LLMProvider):
    engine_id = "onnx"

    @staticmethod
    def _onnxruntime_package(torch_profile: str) -> str:
        return "onnxruntime" if str(torch_profile or "") == "cpu" else "onnxruntime-gpu"

    @staticmethod
    def _optimum_onnx_package(torch_profile: str) -> str:
        extra = "onnxruntime" if str(torch_profile or "") == "cpu" else "onnxruntime-gpu"
        return f"optimum-onnx[{extra}]"

    @staticmethod
    def _resolve_execution_provider(
        value: Any, *, file_name: str | None = None, loader: str | None = None
    ) -> str:
        requested = str(value or "auto").strip()
        if requested and requested.lower() != "auto":
            return requested
        if str(loader or "").strip() == "optimum_feature_extraction":
            return "CPUExecutionProvider"
        if "quantized" in str(file_name or "").lower():
            return "CPUExecutionProvider"
        onnxruntime = ensure_import("onnxruntime", dependency_key="onnx")
        available = list(onnxruntime.get_available_providers() or [])
        if "CUDAExecutionProvider" in available:
            return "CUDAExecutionProvider"
        return "CPUExecutionProvider"

    @classmethod
    def _huggingface_hub_version_supported(cls) -> bool:
        try:
            version = importlib.metadata.version("huggingface-hub")
        except importlib.metadata.PackageNotFoundError:
            return False
        parts = version.split("+", 1)[0].split(".", 2)
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
        except (TypeError, ValueError):
            return False
        return major == 0 and minor >= 34

    @classmethod
    def _missing_module_labels(cls) -> list[str]:
        checks = [
            ("diffusers", "diffusers"),
            ("optimum", "optimum[onnxruntime]"),
            ("sentence_transformers", "sentence-transformers"),
            ("transformers", "transformers"),
        ]
        missing_local: list[str] = []
        for module_name, label in checks:
            found = importlib.util.find_spec(module_name) is not None
            if not found:
                missing_local.append(label)
        if not cls._huggingface_hub_version_supported():
            missing_local.append("huggingface-hub>=0.34,<1.0")
        try:
            torch_ready = torch_runtime_matches_plan()
        except Exception:
            torch_ready = False
        if not torch_ready:
            missing_local.append("PyTorch runtime")
        return missing_local

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
        onnxruntime_package = cls._onnxruntime_package(torch_plan.profile)
        optimum_onnx_package = cls._optimum_onnx_package(torch_plan.profile)
        install_python_packages(
            [
                "diffusers",
                "accelerate",
                "safetensors",
                "huggingface-hub>=0.34,<1.0",
                "optimum",
                optimum_onnx_package,
                onnxruntime_package,
                "sentence-transformers",
                "transformers",
            ],
            modules=[
                "diffusers",
                "optimum.onnxruntime",
                "sentence_transformers",
                "transformers",
            ],
            force=force,
            extra_index_url=torch_plan.index_url,
            extra_pip_args=["--constraint", torch_constraint],
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_module_labels(),
            ok_message="ONNX engine ready",
            error_message="ONNX engine requires shared state or local dependencies",
        )

    @classmethod
    def _validate_config(
        cls, *, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "ready": True,
            "missing_config": [],
            "message": "",
        }

    def __init__(self, config: dict):
        super().__init__(config)

        model_ref = config.get("model_path") or self.model_name
        if not model_ref:
            raise ValueError("OnnxEngine requires 'model' or 'model_path' in config")
        self.model_ref = model_ref
        self.runtime_task = str(config.get("task") or "text-generation").strip()
        self.loader = str(config.get("loader") or "optimum_causal_lm").strip()
        self.subfolder = str(config.get("subfolder") or "").strip()
        self.file_name = str(config.get("file_name") or "").strip() or None
        self.requested_execution_provider = str(
            config.get("execution_provider") or "auto"
        ).strip()
        self.execution_provider = self._resolve_execution_provider(
            self.requested_execution_provider,
            file_name=self.file_name,
            loader=self.loader,
        )
        self.session_options = self._session_options(config.get("session_options"))
        self.provider_options = config.get("provider_options") or None
        self.tokenizer = None
        self.model = None
        self.pipeline = None
        self._streamer_cls = None
        self._load_runtime(model_ref)

    def _ort_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "provider": self.execution_provider,
            "provider_options": self.provider_options,
            "session_options": self.session_options,
        }
        if self.subfolder:
            kwargs["subfolder"] = self.subfolder
        if self.file_name:
            kwargs["file_name"] = self.file_name
        return {key: value for key, value in kwargs.items() if value is not None}

    def _load_runtime(self, model_ref: str) -> None:
        optimum_ort = ensure_import("optimum.onnxruntime", dependency_key="onnx")
        transformers = ensure_import("transformers", dependency_key="transformers")
        AutoTokenizer = transformers.AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_ref)
        if self.loader == "sentence_transformers_cross_encoder":
            sentence_transformers = ensure_import(
                "sentence_transformers",
                dependency_key="sentence-transformers",
            )
            CrossEncoder = sentence_transformers.CrossEncoder
            self.model = CrossEncoder(model_ref, backend="onnx")
            return
        if self.loader == "optimum_feature_extraction":
            self.model = optimum_ort.ORTModelForFeatureExtraction.from_pretrained(
                model_ref,
                **self._ort_kwargs(),
            )
            return
        if self.loader == "optimum_sequence_classification":
            self.model = optimum_ort.ORTModelForSequenceClassification.from_pretrained(
                model_ref,
                **self._ort_kwargs(),
            )
            return
        if self.loader == "optimum_token_classification":
            self.model = optimum_ort.ORTModelForTokenClassification.from_pretrained(
                model_ref,
                **self._ort_kwargs(),
            )
            return
        if self.loader != "optimum_causal_lm":
            raise ValueError(f"unsupported_onnx_loader:{self.loader}")
        self.model = optimum_ort.ORTModelForCausalLM.from_pretrained(
            model_ref,
            **self._ort_kwargs(),
        )
        self._streamer_cls = transformers.TextIteratorStreamer

    def _session_options(self, value: Any) -> Any:
        if not value:
            return None
        if not isinstance(value, dict):
            return value
        onnxruntime = ensure_import("onnxruntime", dependency_key="onnx")
        options = onnxruntime.SessionOptions()
        for key, raw in value.items():
            if hasattr(options, str(key)):
                setattr(options, str(key), raw)
        return options

    async def _generate_completion(
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        generated_text = await asyncio.to_thread(self._generate_text, messages, options)
        return CompletionResponse(
            id="onnx",
            content=generated_text,
            role=MessageRole.ASSISTANT,
            finish_reason="stop",
        )

    async def _generate_stream(
        self, messages: List[Message], options: CompletionOptions
    ) -> AsyncGenerator[StreamChunk, None]:
        prompt = self._format_prompt(messages)
        inputs = self.tokenizer(prompt, return_tensors="pt")
        streamer = self._streamer_cls(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )
        generation_kwargs = self._build_generation_kwargs(options)
        generation_kwargs.update(inputs)
        generation_kwargs["streamer"] = streamer
        context = contextvars.copy_context()
        worker = Thread(
            target=lambda: context.run(self.model.generate, **generation_kwargs),
            daemon=True,
        )
        worker.start()
        for chunk in streamer:
            if chunk:
                yield StreamChunk(id="onnx", delta=chunk)
            await asyncio.sleep(0)

    def _generate_text(
        self, messages: List[Message], options: CompletionOptions
    ) -> str:
        prompt = self._format_prompt(messages)
        inputs = self.tokenizer(prompt, return_tensors="pt")
        generation_kwargs = self._build_generation_kwargs(options)
        output_ids = self.model.generate(**inputs, **generation_kwargs)
        generated = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
        if generated.startswith(prompt):
            return generated[len(prompt) :].strip()
        return generated.strip()

    def _build_generation_kwargs(self, options: CompletionOptions) -> dict[str, Any]:
        return {
            "temperature": options.temperature,
            "top_p": options.top_p,
            "max_new_tokens": options.max_tokens or 256,
            "do_sample": options.temperature > 0,
            "eos_token_id": self.tokenizer.eos_token_id,
            "pad_token_id": (
                self.tokenizer.pad_token_id
                if self.tokenizer.pad_token_id is not None
                else self.tokenizer.eos_token_id
            ),
        }

    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        if self.loader != "optimum_feature_extraction":
            return await super()._embed_texts(texts)
        if not texts:
            return []
        return await asyncio.to_thread(self._embed_texts_sync, texts)

    def _embed_texts_sync(self, texts: List[str]) -> EngineMethodResponse:
        import torch

        encoded = self.tokenizer(
            [str(text or "") for text in texts],
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        outputs = self.model(**encoded)
        hidden = getattr(outputs, "last_hidden_state", None)
        if hidden is None and isinstance(outputs, tuple) and outputs:
            hidden = outputs[0]
        if hidden is None:
            raise RuntimeError("onnx_embedding_missing_hidden_state")
        attention_mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
        pooled = torch.sum(hidden * attention_mask, dim=1) / torch.clamp(
            attention_mask.sum(dim=1),
            min=1e-9,
        )
        if bool(self.config.get("normalize", True)):
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        vectors = pooled.detach().cpu().tolist()
        prompt_tokens = int(encoded["attention_mask"].sum().item())
        dimensions = len(vectors[0]) if vectors else 0
        return EngineMethodResponse(
            result=vectors,
            usage=EngineUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=prompt_tokens,
            ),
            metadata={
                "input_count": len(texts),
                "items": len(vectors),
                "dimensions": dimensions,
            },
        )

    async def _rerank(
        self,
        query: str,
        texts: List[str],
        options: RerankOptions,
    ) -> List[RerankResult]:
        if self.loader != "sentence_transformers_cross_encoder":
            return await super()._rerank(query, texts, options)
        if not texts:
            return []
        prepared_texts = [
            self._rerank_text_for_prediction(str(text or ""), options)
            for text in texts
        ]
        scores = await asyncio.to_thread(
            self.model.predict,
            [(str(query or ""), text) for text in prepared_texts],
        )
        values = scores.tolist() if hasattr(scores, "tolist") else list(scores)
        results = [
            RerankResult(index=index, text=str(text or ""), score=float(score))
            for index, (text, score) in enumerate(zip(texts, values))
        ]
        sorted_results = sorted(results, key=lambda item: item.score, reverse=True)
        if options.top_k is not None and int(options.top_k) > 0:
            return sorted_results[: int(options.top_k)]
        return sorted_results

    def _rerank_text_for_prediction(
        self,
        text: str,
        options: RerankOptions,
    ) -> str:
        if options.max_tokens_per_doc is None or int(options.max_tokens_per_doc) <= 0:
            return text
        tokenizer = getattr(self.model, "tokenizer", None)
        if tokenizer is None:
            return text
        token_ids = tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=True,
            max_length=int(options.max_tokens_per_doc),
        )
        return str(tokenizer.decode(token_ids, skip_special_tokens=True))

    async def _classify(
        self,
        texts: List[str],
        options: ClassificationOptions,
    ) -> List[ClassificationResult]:
        if self.loader != "optimum_sequence_classification":
            return await super()._classify(texts, options)
        if not texts:
            return []
        return await asyncio.to_thread(self._classify_sync, texts, options)

    def _classify_sync(
        self,
        texts: List[str],
        options: ClassificationOptions,
    ) -> List[ClassificationResult]:
        import torch

        encoded = self.tokenizer(
            [str(text or "") for text in texts],
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        outputs = self.model(**encoded)
        function_name = str(options.function_to_apply or "default").strip().lower()
        if function_name == "sigmoid":
            probabilities = torch.sigmoid(outputs.logits)
        elif function_name == "none":
            probabilities = outputs.logits
        else:
            probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
        id2label = getattr(self.model.config, "id2label", {}) or {}
        results: List[ClassificationResult] = []
        for row in probabilities:
            best_index = int(torch.argmax(row).item())
            scores = {
                str(id2label.get(index, index)): float(value)
                for index, value in enumerate(row.detach().cpu().tolist())
            }
            if options.top_k is not None and int(options.top_k) > 0:
                sorted_scores = sorted(
                    scores.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
                scores = dict(sorted_scores[: int(options.top_k)])
            results.append(
                ClassificationResult(
                    label=str(id2label.get(best_index, best_index)),
                    score=float(row[best_index].item()),
                    scores=scores,
                )
            )
        return results

    async def _extract_tokens(self, text: str) -> List[TokenExtractionResult]:
        if self.loader != "optimum_token_classification":
            return await super()._extract_tokens(text)
        if not text:
            return []
        return await asyncio.to_thread(self._extract_tokens_sync, text)

    def _extract_tokens_sync(self, text: str) -> EngineMethodResponse:
        import torch

        encoded = self.tokenizer(
            str(text or ""),
            truncation=True,
            return_offsets_mapping=True,
            return_tensors="pt",
        )
        offsets = encoded.pop("offset_mapping")[0].tolist()
        input_ids = encoded["input_ids"][0].tolist()
        outputs = self.model(**encoded)
        probabilities = torch.nn.functional.softmax(outputs.logits[0], dim=-1)
        id2label = getattr(self.model.config, "id2label", {}) or {}
        results: List[TokenExtractionResult] = []
        special_ids = set(self.tokenizer.all_special_ids or [])
        for token_id, offset, row in zip(input_ids, offsets, probabilities):
            if token_id in special_ids:
                continue
            best_index = int(torch.argmax(row).item())
            label = str(id2label.get(best_index, best_index))
            if label == "O":
                continue
            start, end = int(offset[0]), int(offset[1])
            if end <= start:
                continue
            results.append(
                TokenExtractionResult(
                    token=str(text[start:end]),
                    label=label,
                    score=float(row[best_index].item()),
                    start=start,
                    end=end,
                )
            )
        prompt_tokens = int(encoded["attention_mask"].sum().item())
        return EngineMethodResponse(
            result=results,
            usage=EngineUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=prompt_tokens,
            ),
            metadata={
                "input_count": 1,
                "extracted_items": len(results),
            },
        )

    def _format_prompt(self, messages: List[Message]) -> str:
        if hasattr(self.tokenizer, "apply_chat_template"):
            try:
                payload = []
                for msg in messages:
                    content = (
                        msg.content
                        if isinstance(msg.content, str)
                        else "".join(
                            part.text or ""
                            for part in (msg.content or [])
                            if getattr(part, "type", None) == "text"
                        )
                    )
                    payload.append({"role": msg.role.value, "content": content or ""})
                return self.tokenizer.apply_chat_template(
                    payload, tokenize=False, add_generation_prompt=True
                )
            except Exception:
                pass
        chunks: list[str] = []
        for msg in messages:
            role = (
                "System"
                if msg.role == MessageRole.SYSTEM
                else "User"
                if msg.role == MessageRole.USER
                else "Assistant"
                if msg.role == MessageRole.ASSISTANT
                else "Tool"
            )
            content = (
                msg.content
                if isinstance(msg.content, str)
                else "".join(
                    part.text or ""
                    for part in (msg.content or [])
                    if getattr(part, "type", None) == "text"
                )
            )
            chunks.append(f"{role}: {content or ''}")
        chunks.append("Assistant:")
        return "\n".join(chunks)

    def get_info(self) -> dict:
        info = super().get_info()
        info.update(
            {
                "execution_provider": self.execution_provider,
                "requested_execution_provider": self.requested_execution_provider,
                "resolved_execution_provider": self.execution_provider,
                "tool_calling_supported": False,
            }
        )
        return info

    def cleanup(self):
        pass
