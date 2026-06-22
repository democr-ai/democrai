import asyncio
import importlib
import io
import tempfile
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any, AsyncGenerator

from democrai.sdk.engines import (
    BaseEngine,
    BaseTTSProvider,
    EngineStreamFinal,
    EngineUsage,
)
from democrai.sdk.dependencies import (
    ensure_import,
    install_python_packages,
    resolve_torch_runtime_plan,
)


_TORCH_PACKAGES = ("torch==2.10.0", "torchaudio==2.10.0")
_TORCH_MODULES = ("torch", "torchaudio")
_PARLER_PACKAGE = "git+https://github.com/huggingface/parler-tts.git"
_PARLER_DISTRIBUTION = "parler_tts"
_PARLER_VERSION = "0.2.2"
_TRANSFORMERS_PACKAGE = "transformers==4.46.1"
_TRANSFORMERS_VERSION = "4.46.1"
_PARLER_PACKAGES = (
    _PARLER_PACKAGE,
    _TRANSFORMERS_PACKAGE,
    "accelerate",
    "soundfile",
    "sentencepiece",
    "protobuf>=4.0.0",
)
_PARLER_CONSTRAINTS = (
    "numpy<2.5",
)
_PARLER_MODULES = (
    "parler_tts",
    "transformers",
    "soundfile",
    "sentencepiece",
)


class ParlerEngine(BaseEngine, BaseTTSProvider):
    engine_id = "parler"

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
        constraints_path = cls._write_install_constraints()
        install_python_packages(
            [
                *torch_plan.packages,
                *_PARLER_PACKAGES,
            ],
            modules=[*torch_plan.modules, *_PARLER_MODULES],
            force=True,
            allow_source=True,
            extra_index_url=torch_plan.index_url,
            extra_pip_args=["--constraint", constraints_path],
        )

    @staticmethod
    def _write_install_constraints() -> str:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix="parler-constraints-",
            suffix=".txt",
            delete=False,
        ) as handle:
            handle.write("\n".join(_PARLER_CONSTRAINTS))
            handle.write("\n")
            return handle.name

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        missing_local = cls._missing_modules(
            ("torch", "torch"),
            ("torchaudio", "torchaudio"),
            ("parler_tts", "parler-tts"),
            ("transformers", _TRANSFORMERS_PACKAGE),
            ("soundfile", "soundfile"),
            ("sentencepiece", "sentencepiece"),
        )
        missing_local.extend(cls._missing_chain_versions())
        if not cls._parler_runtime_supported():
            missing_local.append("parler_tts runtime")
        if not cls._transformers_runtime_supported():
            missing_local.append(_TRANSFORMERS_PACKAGE)
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=missing_local,
            ok_message="Parler engine ready",
            error_message="Parler engine requires shared state or local dependencies",
        )

    @staticmethod
    def _package_version_exact(distribution_name: str, expected: str) -> bool:
        try:
            installed = version(distribution_name)
        except PackageNotFoundError:
            return False
        return installed.split("+", 1)[0] == expected

    @classmethod
    def _missing_chain_versions(cls) -> list[str]:
        checks = (
            ("torch", "2.10.0", "torch==2.10.0"),
            ("torchaudio", "2.10.0", "torchaudio==2.10.0"),
            (_PARLER_DISTRIBUTION, _PARLER_VERSION, f"parler-tts=={_PARLER_VERSION}"),
            ("transformers", _TRANSFORMERS_VERSION, _TRANSFORMERS_PACKAGE),
        )
        missing: list[str] = []
        for distribution_name, expected_version, label in checks:
            if not cls._package_version_exact(distribution_name, expected_version):
                missing.append(label)
        return missing

    @staticmethod
    def _parler_runtime_supported() -> bool:
        try:
            parler_mod = importlib.import_module("parler_tts")
        except Exception:
            return False
        return hasattr(parler_mod, "ParlerTTSForConditionalGeneration") and hasattr(
            parler_mod,
            "ParlerTTSConfig",
        )

    @staticmethod
    def _transformers_runtime_supported() -> bool:
        try:
            transformers_mod = importlib.import_module("transformers")
        except Exception:
            return False
        return all(
            hasattr(transformers_mod, name)
            for name in ("AutoTokenizer", "AutoFeatureExtractor", "GenerationConfig")
        )

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)

        torch = ensure_import("torch", dependency_key="torch")
        parler_mod = ensure_import("parler_tts", dependency_key="parler_tts")
        transformers_mod = ensure_import("transformers", dependency_key="transformers")
        self._ParlerTTSForConditionalGeneration = (
            parler_mod.ParlerTTSForConditionalGeneration
        )
        self._ParlerTTSConfig = parler_mod.ParlerTTSConfig
        self._AutoTokenizer = transformers_mod.AutoTokenizer
        self._AutoFeatureExtractor = transformers_mod.AutoFeatureExtractor
        self._GenerationConfig = transformers_mod.GenerationConfig
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        repo_id = (
            config.get("model_path") or self.model_name or config.get("model_name")
        )
        if not repo_id:
            raise RuntimeError("parler_model_required")
        revision = self.model_revision or "main"
        model_config = self._model_config(config)
        self.model = self._ParlerTTSForConditionalGeneration.from_pretrained(
            repo_id,
            config=model_config,
        ).to(self.device)
        self._apply_generation_config(config)
        self.tokenizer = self._AutoTokenizer.from_pretrained(repo_id, revision=revision)
        self.feature_extractor = self._AutoFeatureExtractor.from_pretrained(
            repo_id, revision=revision
        )

    async def synthesize(self, text: str, options: Any):
        description = str(options.voice or self.config.get("voice") or "")
        if not description:
            raise RuntimeError("parler_voice_description_required")

        def _generate():
            sf = ensure_import("soundfile", dependency_key="soundfile")
            input_ids = self.tokenizer(description, return_tensors="pt").input_ids.to(
                self.device
            )
            prompt_input_ids = self.tokenizer(text, return_tensors="pt").input_ids.to(
                self.device
            )
            generation = self.model.generate(
                input_ids=input_ids, prompt_input_ids=prompt_input_ids
            )
            audio_arr = generation.cpu().numpy().squeeze()
            buffer = io.BytesIO()
            sf.write(buffer, audio_arr, self.model.config.sampling_rate, format="WAV")
            return buffer.getvalue()

        audio_data = await asyncio.to_thread(_generate)
        prompt_tokens = self._prompt_tokens(description=description, text=text)
        return {
            "data": audio_data,
            "content_type": "audio/wav",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "total_tokens": prompt_tokens,
            },
            "usage_metadata": {
                "usage_source": "tokenizer",
                "usage_calculation": "engines.parler.engine.ParlerEngine._token_count",
            },
        }

    async def synthesize_stream(
        self, text: str, options: Any
    ) -> AsyncGenerator[bytes | EngineStreamFinal, None]:
        started_at = time.perf_counter()
        resp = await self.synthesize(text, options)
        duration_ms = self._duration_ms(started_at)
        yield resp["data"]
        usage = dict(resp.get("usage") or {})
        total_tokens = int(usage.get("total_tokens") or 0)
        yield EngineStreamFinal(
            usage=EngineUsage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=0,
                total_tokens=total_tokens,
            ),
            duration_ms=duration_ms,
            tokens_per_second=self._tokens_per_second(total_tokens, duration_ms),
            metadata=dict(resp.get("usage_metadata") or {}),
        )

    def _model_config(self, config: dict[str, Any]):
        parler_config = config.get("parler_config")
        if not isinstance(parler_config, dict):
            raise RuntimeError("parler_model_config_required")
        return self._ParlerTTSConfig(**parler_config)

    def _apply_generation_config(self, config: dict[str, Any]) -> None:
        generation_config = config.get("parler_generation_config")
        if not isinstance(generation_config, dict):
            raise RuntimeError("parler_generation_config_required")
        self.model.generation_config = self._GenerationConfig(**generation_config)

    def _token_count(self, text: str) -> int:
        encoded = self.tokenizer(str(text or ""), return_tensors="pt")
        input_ids = getattr(encoded, "input_ids", None)
        if input_ids is None:
            return 0
        try:
            return int(input_ids.shape[-1])
        except Exception:
            return 0

    def _prompt_tokens(self, *, description: str, text: str) -> int:
        return self._token_count(description) + self._token_count(text)

    @staticmethod
    def _tokens_per_second(total_tokens: int, duration_ms: float) -> float:
        if total_tokens <= 0 or duration_ms <= 0:
            return 0.0
        return round(float(total_tokens) / (float(duration_ms) / 1000.0), 2)

    @staticmethod
    def _duration_ms(started_at: float) -> float:
        return max(0.01, round((time.perf_counter() - started_at) * 1000.0, 2))
