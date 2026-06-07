from __future__ import annotations

import asyncio
import hashlib
import importlib
from importlib.metadata import PackageNotFoundError, version
import io
import math
import os
import shutil
import tempfile
import time
from pathlib import Path
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
from democrai.sdk.engine_runtime_media import (
    materialize_media,
    media_exists,
    save_model_artifact,
)

import logging

logger = logging.getLogger("qwen_tts")

TOKENIZER_REPO = "Qwen/Qwen3-TTS-Tokenizer-12Hz"
TOKENIZER_MODEL_ID = "qwen3-tts-tokenizer-12hz"
_TORCH_PACKAGES = ("torch==2.10.0", "torchaudio==2.10.0")
_TORCH_MODULES = ("torch", "torchaudio")
_QWEN_TTS_PACKAGE = "qwen-tts==0.1.1"
_QWEN_TTS_VERSION = "0.1.1"
_TRANSFORMERS_PACKAGE = "transformers==4.57.3"
_TRANSFORMERS_VERSION = "4.57.3"
_ACCELERATE_PACKAGE = "accelerate==1.12.0"
_ACCELERATE_VERSION = "1.12.0"
_QWEN_TTS_PACKAGES = (
    _QWEN_TTS_PACKAGE,
    _TRANSFORMERS_PACKAGE,
    _ACCELERATE_PACKAGE,
    "soundfile",
    "huggingface-hub",
    "sox",
    "onnxruntime",
    "einops",
)
_QWEN_TTS_MODULES = (
    "qwen_tts",
    "soundfile",
    "transformers",
    "huggingface_hub",
    "sox",
    "onnxruntime",
    "einops",
)
INTEGER_GENERATION_OPTIONS = {
    "top_k",
    "max_new_tokens",
    "subtalker_top_k",
}


class QwenTTSEngine(BaseEngine, BaseTTSProvider):
    engine_id = "qwen_tts"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> dict[str, Any]:
        torch_plan = resolve_torch_runtime_plan(
            packages=_TORCH_PACKAGES,
            modules=_TORCH_MODULES,
        )
        install_python_packages(
            [
                *torch_plan.packages,
                *_QWEN_TTS_PACKAGES,
            ],
            modules=[*torch_plan.modules, *_QWEN_TTS_MODULES],
            force=True,
            extra_index_url=torch_plan.index_url,
        )
        tokenizer_path = cls._install_tokenizer(force=force)
        return {
            "config_updates": {
                "tokenizer_path": tokenizer_path,
                "tokenizer_ref": TOKENIZER_REPO,
            }
        }

    @classmethod
    def _install_tokenizer(cls, *, force: bool = False) -> str:
        existing_path = cls._configured_tokenizer_path()
        if existing_path and not force:
            return existing_path
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        huggingface_hub = importlib.import_module("huggingface_hub")
        return str(
            huggingface_hub.snapshot_download(
                repo_id=TOKENIZER_REPO,
                local_dir_use_symlinks=False,
                max_workers=1,
            )
        )

    @classmethod
    def _configured_tokenizer_path(cls) -> str:
        hub_cache = str(os.environ.get("HF_HUB_CACHE") or "").strip()
        if not hub_cache:
            return ""
        snapshots_dir = (
            Path(hub_cache)
            / "models--Qwen--Qwen3-TTS-Tokenizer-12Hz"
            / "snapshots"
        )
        if not snapshots_dir.is_dir():
            return ""
        snapshots = [path for path in snapshots_dir.iterdir() if path.is_dir()]
        if not snapshots:
            return ""
        return str(max(snapshots, key=lambda path: path.stat().st_mtime))

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        missing_local = cls._missing_modules(
            ("qwen_tts", "qwen-tts"),
            ("torch", "torch"),
            ("torchaudio", "torchaudio"),
            ("soundfile", "soundfile"),
            ("transformers", _TRANSFORMERS_PACKAGE),
            ("huggingface_hub", "huggingface-hub"),
            ("sox", "sox"),
            ("onnxruntime", "onnxruntime"),
            ("einops", "einops"),
        )
        missing_local.extend(cls._missing_chain_versions())
        if not cls._qwen_runtime_supported():
            logging.error("NO RUNTIME")
            missing_local.append("qwen_tts runtime")
        if not cls._transformers_runtime_supported():
            logging.error("NO TRANSFORMERS")
            missing_local.append(_TRANSFORMERS_PACKAGE)
        try:
            tokenizer_configured = bool(cls._configured_tokenizer_path())
        except Exception:
            tokenizer_configured = False
            logging.error("NO TOKENIZER")
        if not tokenizer_configured:
            missing_local.append("Qwen3-TTS tokenizer")
            logging.error("NO TOKENIZER CONFIGURED")
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=missing_local,
            ok_message="Qwen TTS engine ready",
            error_message="Qwen TTS engine requires shared state or local dependencies",
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
            ("qwen-tts", _QWEN_TTS_VERSION, _QWEN_TTS_PACKAGE),
            ("transformers", _TRANSFORMERS_VERSION, _TRANSFORMERS_PACKAGE),
            ("accelerate", _ACCELERATE_VERSION, _ACCELERATE_PACKAGE),
        )
        missing: list[str] = []
        for distribution_name, expected_version, label in checks:
            if not cls._package_version_exact(distribution_name, expected_version):
                missing.append(label)
        return missing

    @staticmethod
    def _qwen_runtime_supported() -> bool:
        try:
            qwen_tts_mod = importlib.import_module("qwen_tts")
            model_mod = importlib.import_module("qwen_tts.inference.qwen3_tts_model")
        except Exception:
            return False
        return hasattr(qwen_tts_mod, "Qwen3TTSModel") and hasattr(
            model_mod, "VoiceClonePromptItem"
        )

    @staticmethod
    def _transformers_runtime_supported() -> bool:
        try:
            transformers_mod = importlib.import_module("transformers")
        except Exception:
            return False
        return all(
            hasattr(transformers_mod, name)
            for name in ("AutoModel", "AutoTokenizer", "GenerationConfig")
        )

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)

        torch = ensure_import("torch", dependency_key="torch")
        qwen_tts_mod = ensure_import("qwen_tts", dependency_key="qwen_tts")
        self._sf = ensure_import("soundfile", dependency_key="soundfile")
        self._patch_sox_transformer_if_needed()
        self._torch = torch
        self._Qwen3TTSModel = qwen_tts_mod.Qwen3TTSModel
        model_name = (
            config.get("model_path")
            or self.model_name
            or config.get("model_name")
            or "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
        )
        dtype_name = str(config.get("dtype") or "auto").strip().lower()
        device_map = config.get("device_map", "auto")
        torch_dtype: Any = None
        if dtype_name == "auto":
            torch_dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        elif hasattr(torch, dtype_name):
            torch_dtype = getattr(torch, dtype_name)
        kwargs: dict[str, Any] = {"device_map": device_map}
        if torch_dtype is not None:
            kwargs["torch_dtype"] = torch_dtype
        attn_implementation = str(config.get("attn_implementation") or "").strip()
        if attn_implementation:
            kwargs["attn_implementation"] = attn_implementation
        self.model = self._Qwen3TTSModel.from_pretrained(model_name, **kwargs)
        self.runtime_method = str(
            config.get("qwen_tts_method") or "custom_voice"
        ).strip()
        self.default_voice = str(config.get("voice") or "")
        self.default_language = str(config.get("language") or "auto")
        self.default_instruction = str(config.get("instruction") or "")
        self.default_non_streaming_mode = bool(config.get("non_streaming_mode", True))
        self.tokenizer = self.model.processor.tokenizer
        self.voice_clone_prompt = None
        self.generation_defaults = {}
        for key in (
            "do_sample",
            "top_k",
            "top_p",
            "temperature",
            "repetition_penalty",
            "max_new_tokens",
            "subtalker_dosample",
            "subtalker_top_k",
            "subtalker_top_p",
            "subtalker_temperature",
        ):
            if key not in config:
                continue
            value = config[key]
            if key in INTEGER_GENERATION_OPTIONS and value is not None:
                value = int(value)
            self.generation_defaults[key] = value
        if self.runtime_method == "voice_clone":
            self.voice_clone_prompt = self._voice_clone_prompt_from_config(config)

    @staticmethod
    def _patch_sox_transformer_if_needed() -> None:
        if shutil.which("sox"):
            return
        sox_mod = ensure_import("sox", dependency_key="sox")

        class _InProcessTransformer:
            def __init__(self):
                self._db_level = None

            def norm(self, db_level: float = -6.0):
                self._db_level = float(db_level)
                return self

            def build_array(self, *, input_array, sample_rate_in: int):
                numpy = ensure_import("numpy", dependency_key="numpy")
                audio = numpy.asarray(input_array, dtype=numpy.float32)
                peak = float(numpy.max(numpy.abs(audio))) if audio.size else 0.0
                if peak <= 0.0:
                    return audio
                target = math.pow(10.0, float(self._db_level or -6.0) / 20.0)
                return numpy.clip(audio * (target / peak), -1.0, 1.0).astype(
                    numpy.float32
                )

        sox_mod.Transformer = _InProcessTransformer

    def _voice_clone_prompt_from_config(self, config: dict[str, Any]) -> Any:
        artifact_path = self._voice_clone_prompt_artifact_path(config)
        if artifact_path and self._media_storage_exists(artifact_path):
            return self._load_voice_clone_prompt_artifact(artifact_path)

        storage_path = str(
            config.get("voice_clone_ref_audio_storage_path") or ""
        ).strip()
        if not storage_path:
            storage_path = self._first_upload_storage_path(
                config.get("voice_clone_ref_audio")
            )
        if not storage_path:
            return None

        ref_text = str(config.get("voice_clone_ref_text") or "").strip()
        x_vector_only_mode = bool(config.get("voice_clone_x_vector_only_mode", False))
        if not x_vector_only_mode and not ref_text:
            raise RuntimeError("qwen_tts_voice_clone_ref_text_required")

        materialized = materialize_media(storage_path)
        try:
            prompt_items = self.model.create_voice_clone_prompt(
                ref_audio=str(materialized.path),
                ref_text=ref_text or None,
                x_vector_only_mode=x_vector_only_mode,
            )
        finally:
            materialized.cleanup()
        if artifact_path:
            self._save_voice_clone_prompt_artifact(
                artifact_path,
                prompt_items,
            )
        return prompt_items

    def _voice_clone_prompt_artifact_path(self, config: dict[str, Any]) -> str:
        configured = str(config.get("voice_clone_prompt_storage_path") or "").strip()
        if configured:
            return configured
        storage_path = str(
            config.get("voice_clone_ref_audio_storage_path") or ""
        ).strip()
        if not storage_path:
            storage_path = self._first_upload_storage_path(
                config.get("voice_clone_ref_audio")
            )
        if not storage_path:
            return ""
        fingerprint = hashlib.sha256(
            "|".join(
                [
                    str(config.get("model") or config.get("model_path") or ""),
                    storage_path,
                    str(config.get("voice_clone_ref_text") or ""),
                    str(bool(config.get("voice_clone_x_vector_only_mode", False))),
                ]
            ).encode("utf-8")
        ).hexdigest()[:24]
        return f"models/qwen_tts_voice_clones_{fingerprint}/voice_clone_prompt.pt"

    def _media_storage_exists(self, storage_path: str) -> bool:
        return media_exists(storage_path)

    def _load_voice_clone_prompt_artifact(self, storage_path: str) -> Any:
        materialized = materialize_media(storage_path)
        try:
            prompt_item_cls = getattr(
                ensure_import(
                    "qwen_tts.inference.qwen3_tts_model",
                    dependency_key="qwen_tts",
                ),
                "VoiceClonePromptItem",
            )
            with self._torch.serialization.safe_globals([prompt_item_cls]):
                return self._torch.load(
                    str(materialized.path),
                    map_location="cpu",
                    weights_only=True,
                )
        finally:
            materialized.cleanup()

    def _save_voice_clone_prompt_artifact(
        self,
        storage_path: str,
        voice_clone_prompt: Any,
    ) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as handle:
            tmp_path = handle.name
        try:
            self._torch.save(voice_clone_prompt, tmp_path)
            save_model_artifact(storage_path, tmp_path)
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _first_upload_storage_path(value: Any) -> str:
        item: dict[str, Any] = {}
        if isinstance(value, list) and value and isinstance(value[0], dict):
            item = dict(value[0])
        elif isinstance(value, dict):
            item = dict(value)
        return str(item.get("storage_path") or item.get("path") or "").strip()

    def _build_kwargs(self, text: str, options: Any) -> dict[str, Any]:
        payload = {
            "text": str(text or ""),
            "language": self.default_language,
            "non_streaming_mode": self.default_non_streaming_mode,
            **self.generation_defaults,
        }
        instruction = self.default_instruction.strip()
        if self.runtime_method == "custom_voice":
            payload["speaker"] = str(options.voice or self.default_voice)
        elif self.runtime_method == "voice_design":
            if not instruction:
                raise RuntimeError("qwen_tts_voice_design_instruction_required")
        elif self.runtime_method == "voice_clone":
            if self.voice_clone_prompt is None:
                raise RuntimeError("qwen_tts_voice_clone_not_configured")
            payload["voice_clone_prompt"] = self.voice_clone_prompt
        else:
            raise RuntimeError(f"qwen_tts_method_unsupported:{self.runtime_method}")
        if instruction and self.runtime_method in {"custom_voice", "voice_design"}:
            payload["instruct"] = instruction
        return payload

    @staticmethod
    def _extract_audio_and_sr(output: Any) -> tuple[Any, int]:
        if isinstance(output, dict):
            audio = output.get("audio")
            if audio is None:
                audio = output.get("wav")
            if audio is None:
                audio = output.get("waveform")
            sample_rate = int(
                output.get("sample_rate") or output.get("sampling_rate") or 24000
            )
            if isinstance(audio, list):
                audio = audio[0] if audio else None
            return audio, sample_rate
        if isinstance(output, tuple) and len(output) >= 2:
            audio = output[0]
            if isinstance(audio, list):
                audio = audio[0] if audio else None
            return audio, int(output[1] or 24000)
        return output, 24000

    async def synthesize(self, text: str, options: Any):
        kwargs = self._build_kwargs(text, options)

        def _run() -> bytes:
            if self.runtime_method == "custom_voice":
                generated = self.model.generate_custom_voice(**kwargs)
            elif self.runtime_method == "voice_design":
                generated = self.model.generate_voice_design(**kwargs)
            elif self.runtime_method == "voice_clone":
                generated = self.model.generate_voice_clone(**kwargs)
            else:
                raise RuntimeError(f"qwen_tts_method_unsupported:{self.runtime_method}")
            audio, sample_rate = self._extract_audio_and_sr(generated)
            if audio is None:
                raise RuntimeError("Qwen3-TTS did not return audio data")
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            if hasattr(audio, "cpu") and hasattr(audio, "numpy"):
                audio = audio.cpu().numpy()
            if hasattr(audio, "squeeze"):
                audio = audio.squeeze()
            buf = io.BytesIO()
            self._sf.write(buf, audio, sample_rate, format="WAV")
            return buf.getvalue()

        wav_data = await asyncio.to_thread(_run)
        prompt_tokens = self._usage_prompt_tokens(kwargs)
        return {
            "data": wav_data,
            "content_type": "audio/wav",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "total_tokens": prompt_tokens,
            },
            "usage_metadata": {
                "usage_source": "tokenizer",
                "usage_calculation": "engines.qwen_tts.engine.QwenTTSEngine._usage_prompt_tokens",
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

    def _usage_prompt_tokens(self, kwargs: dict[str, Any]) -> int:
        total = 0
        for key in ("text", "instruct", "speaker", "language"):
            value = kwargs.get(key)
            if value in (None, ""):
                continue
            total += self._token_count(str(value))
        return total

    def _token_count(self, text: str) -> int:
        encoded = self.tokenizer(
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

    @staticmethod
    def _tokens_per_second(total_tokens: int, duration_ms: float) -> float:
        if total_tokens <= 0 or duration_ms <= 0:
            return 0.0
        return round(float(total_tokens) / (float(duration_ms) / 1000.0), 2)

    @staticmethod
    def _duration_ms(started_at: float) -> float:
        return max(0.01, round((time.perf_counter() - started_at) * 1000.0, 2))
