from importlib.metadata import PackageNotFoundError, version
from typing import Any, AsyncGenerator, List

from democrai.sdk.engines import (
    BaseEngine,
    CompletionOptions,
    CompletionResponse,
    CompletionUsage,
    current_ai_call_context,
    Message,
    MessageRole,
    StreamChunk,
    LLMProvider,
)
from democrai.sdk.dependencies import (
    ensure_import,
    install_python_packages,
    resolve_torch_runtime_plan,
)
from democrai.sdk.normalize import normalize_bool
from engines.vllm.messages import chat_messages, chat_template_content_format


_TORCH_PACKAGES = ("torch==2.10.0", "torchvision==0.25.0", "torchaudio==2.10.0")
_TORCH_MODULES = ("torch", "torchvision", "torchaudio")
_VLLM_PACKAGE = "vllm==0.19.1"
_BITSANDBYTES_PACKAGE = "bitsandbytes==0.49.2"
_PILLOW_PACKAGE = "pillow"
_VLLM_MODULES = ["vllm", "bitsandbytes", "PIL"]
_CHAIN_VERSION_CHECKS = {
    "torch": "2.10.0",
    "torchvision": "0.25.0",
    "torchaudio": "2.10.0",
    "vllm": "0.19.1",
    "bitsandbytes": "0.49.2",
}


def _python_supported(env: dict | None) -> bool:
    version = str((env or {}).get("python") or "").strip()
    if not version:
        return True
    parts = version.split(".", 2)
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        return False
    return (major, minor) >= (3, 10) and (major, minor) < (3, 14)


def _platform_supported(env: dict | None) -> bool:
    effective_env = env or {}
    return (
        str(effective_env.get("os") or "").strip().lower() == "linux"
        and str(effective_env.get("arch") or "").strip().lower() == "x86_64"
        and bool(((effective_env.get("gpu") or {}).get("has_nvidia")))
        and int(((effective_env.get("gpu") or {}).get("vram_mb") or 0)) >= 12000
        and _python_supported(effective_env)
    )


class VLLMEngine(BaseEngine, LLMProvider):
    engine_id = "vllm"

    @classmethod
    def _check_supported(cls, env: dict | None = None) -> dict[str, object]:
        supported = _platform_supported(env)
        return cls._build_supported_payload(
            supported=supported,
            reason=cls.unsupported_reason(env),
        )

    @classmethod
    def is_supported(cls, env: dict | None = None) -> bool:
        return _platform_supported(env)

    @classmethod
    def unsupported_reason(cls, env: dict | None = None) -> str:
        if not _python_supported(env):
            return "vLLM requires Python >=3.10,<3.14"
        return "vLLM requires Linux x86_64 with NVIDIA GPU and at least 12 GB VRAM"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        torch_plan = resolve_torch_runtime_plan(
            packages=_TORCH_PACKAGES,
            modules=_TORCH_MODULES,
        )
        install_python_packages(
            [
                *torch_plan.packages,
                _VLLM_PACKAGE,
                _BITSANDBYTES_PACKAGE,
                _PILLOW_PACKAGE,
            ],
            modules=[*torch_plan.modules, *_VLLM_MODULES],
            force=True,
            allow_source=True,
            extra_index_url=torch_plan.index_url,
            extra_pip_args=[
                "--only-binary",
                "vllm,bitsandbytes",
            ],
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, object]:
        missing_local = cls._missing_modules(
            ("vllm", "vllm"),
            ("bitsandbytes", "bitsandbytes"),
            ("PIL", "pillow"),
        )
        missing_local.extend(cls._missing_chain_versions())
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=missing_local,
            ok_message="vLLM engine ready",
            error_message="vLLM engine requires shared state or local dependencies",
        )

    @classmethod
    def _missing_chain_versions(cls) -> list[str]:
        missing: list[str] = []
        for package_name, expected_version in _CHAIN_VERSION_CHECKS.items():
            try:
                installed_version = version(package_name)
            except PackageNotFoundError:
                missing.append(package_name)
                continue
            if installed_version.split("+", 1)[0] != expected_version:
                missing.append(f"{package_name}=={expected_version}")
        return missing

    @classmethod
    def _validate_config(cls, *, config: dict | None = None) -> dict[str, object]:
        return {
            "ready": True,
            "missing_config": [],
            "message": "",
        }

    def __init__(self, config: dict):
        super().__init__(config)

        vllm_mod = ensure_import("vllm", dependency_key="vllm")
        llm_cls = vllm_mod.LLM
        model_path = config.get("model_path") or self.model_name or ""
        if not model_path:
            raise ValueError("VLLMEngine requires 'model' or 'model_path' in config")
        llm_kwargs = {
            "model": str(model_path),
            "trust_remote_code": config.get("trust_remote_code", True),
            "gpu_memory_utilization": config.get(
                "gpu_memory_utilization",
                config.get("gpu_util", 0.9),
            ),
            "dtype": config.get("dtype", "auto"),
        }
        for key in (
            "cpu_offload_gb",
            "enable_prefix_caching",
            "enforce_eager",
            "gpu_memory_utilization",
            "kv_cache_memory_bytes",
            "kv_cache_dtype",
            "kv_offloading_backend",
            "kv_offloading_size",
            "load_format",
            "max_model_len",
            "max_num_batched_tokens",
            "max_num_seqs",
            "offload_group_size",
            "offload_num_in_group",
            "offload_params",
            "offload_prefetch_step",
            "quantization",
            "reasoning_parser",
            "swap_space",
            "trust_remote_code",
        ):
            if key in config and config.get(key) is not None:
                llm_kwargs[key] = config.get(key)
        if "cache_dtype" in config and config.get("cache_dtype") is not None:
            llm_kwargs["kv_cache_dtype"] = config.get("cache_dtype")
        self.llm = llm_cls(**llm_kwargs)
        self._active_request_ids: set[str] = set()

    def cleanup(self):
        pass

    def cancel_request(self, request_id: str) -> None:
        resolved_request_id = str(request_id or "").strip()
        if (
            not resolved_request_id
            or resolved_request_id not in self._active_request_ids
        ):
            return
        self.llm.llm_engine.abort_request([resolved_request_id], internal=True)

    async def _generate_completion(
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        import asyncio
        import time

        vllm_mod = ensure_import("vllm", dependency_key="vllm")
        extra = options.extra
        sampling_kwargs: dict[str, object] = {
            "temperature": options.temperature,
            "top_p": options.top_p,
            "max_tokens": options.max_tokens or 512,
            "stop": options.stop,
        }
        if "top_k" in extra:
            sampling_kwargs["top_k"] = extra["top_k"]
        chat_template_kwargs = {}
        if "reasoning" in extra:
            chat_template_kwargs["enable_thinking"] = _bool_value(extra["reasoning"])
        sampling_params = vllm_mod.SamplingParams(**sampling_kwargs)
        tools = self._completion_tools(options)
        started_at = time.perf_counter()
        engine_input = self.llm._preprocess_chat_one(
            chat_messages(messages),
            chat_template_content_format=chat_template_content_format(messages),
            chat_template_kwargs=chat_template_kwargs,
            tools=tools or None,
        )
        request_id = _request_id()
        self._active_request_ids.add(request_id)
        request_output = None
        try:
            self.llm.llm_engine.add_request(request_id, engine_input, sampling_params)
            while request_output is None:
                for output in self.llm.llm_engine.step():
                    if str(getattr(output, "request_id", "")) == request_id and bool(
                        getattr(output, "finished", False)
                    ):
                        request_output = output
                        break
                await asyncio.sleep(0)
        finally:
            self._active_request_ids.discard(request_id)
        generation_ms = (time.perf_counter() - started_at) * 1000.0
        completion_output = request_output.outputs[0]
        text = completion_output.text
        reasoning = getattr(completion_output, "reasoning_content", None)
        prompt_tokens = len(getattr(request_output, "prompt_token_ids", None) or [])
        completion_tokens = len(getattr(completion_output, "token_ids", None) or [])
        return CompletionResponse(
            id=request_output.request_id,
            content=text,
            reasoning=reasoning,
            role=MessageRole.ASSISTANT,
            usage=CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            tokens_per_second=self._tokens_per_second(
                completion_tokens,
                generation_ms,
            ),
            finish_reason=getattr(completion_output, "finish_reason", None),
        )

    async def _generate_stream(
        self, messages: List[Message], options: CompletionOptions
    ) -> AsyncGenerator[StreamChunk, None]:
        import asyncio
        import time

        vllm_mod = ensure_import("vllm", dependency_key="vllm")
        sampling_mod = ensure_import("vllm.sampling_params", dependency_key="vllm")
        extra = options.extra
        sampling_kwargs: dict[str, object] = {
            "temperature": options.temperature,
            "top_p": options.top_p,
            "max_tokens": options.max_tokens or 512,
            "stop": options.stop,
        }
        if "top_k" in extra:
            sampling_kwargs["top_k"] = extra["top_k"]
        chat_template_kwargs = {}
        if "reasoning" in extra:
            chat_template_kwargs["enable_thinking"] = _bool_value(extra["reasoning"])
        sampling_params = vllm_mod.SamplingParams(
            **sampling_kwargs,
            output_kind=sampling_mod.RequestOutputKind.DELTA,
        )
        engine_input = self.llm._preprocess_chat_one(
            chat_messages(messages),
            chat_template_content_format=chat_template_content_format(messages),
            chat_template_kwargs=chat_template_kwargs,
            tools=self._completion_tools(options) or None,
        )
        request_id = _request_id()
        started_at = time.perf_counter()
        self._active_request_ids.add(request_id)
        self.llm.llm_engine.add_request(request_id, engine_input, sampling_params)
        prompt_tokens: int | None = None
        completion_tokens = 0
        try:
            while True:
                step_outputs = self.llm.llm_engine.step()
                for request_output in step_outputs:
                    if str(getattr(request_output, "request_id", "")) != request_id:
                        continue
                    current_prompt_tokens = len(
                        getattr(request_output, "prompt_token_ids", None) or []
                    )
                    if current_prompt_tokens:
                        prompt_tokens = current_prompt_tokens
                    output = request_output.outputs[0]
                    completion_tokens += len(getattr(output, "token_ids", None) or [])
                    reasoning = str(getattr(output, "reasoning_content", "") or "")
                    if reasoning:
                        yield StreamChunk(
                            id=request_id,
                            reasoning=reasoning,
                            finish_reason=None,
                        )
                    text = str(getattr(output, "text", "") or "")
                    if text:
                        yield StreamChunk(
                            id=request_id,
                            delta=text,
                            finish_reason=None,
                        )
                    if bool(getattr(request_output, "finished", False)):
                        yield StreamChunk(
                            id=request_id,
                            delta=None,
                            finish_reason=getattr(output, "finish_reason", None),
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens or None,
                            total_tokens=(
                                prompt_tokens + completion_tokens
                                if prompt_tokens is not None
                                else None
                            ),
                            tokens_per_second=self._tokens_per_second(
                                completion_tokens,
                                (time.perf_counter() - started_at) * 1000.0,
                            ),
                        )
                        return
                await asyncio.sleep(0)
        finally:
            self._active_request_ids.discard(request_id)

    def _completion_tools(self, options: CompletionOptions) -> list[dict[str, object]]:
        return [tool.model_dump() for tool in list(options.tools or [])]

    def _tokens_per_second(
        self,
        completion_tokens: int | None,
        duration_ms: float | None,
    ) -> float | None:
        if not isinstance(completion_tokens, int) or completion_tokens <= 0:
            return None
        if not isinstance(duration_ms, (int, float)) or duration_ms <= 0:
            return None
        return round(float(completion_tokens) / (float(duration_ms) / 1000.0), 4)


def _bool_value(value: object) -> bool:
    return normalize_bool(value, default=False)


def _request_id() -> str:
    import uuid

    return str(current_ai_call_context().get("request_id") or uuid.uuid4().hex)
