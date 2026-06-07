import asyncio
import importlib
from importlib.metadata import PackageNotFoundError, version
import io
from typing import Any, Optional

from democrai.sdk.engines import BaseEngine, BaseSTTProvider
from democrai.sdk.dependencies import ensure_import, install_python_packages

_FASTER_WHISPER_PACKAGE = "faster-whisper==1.2.1"
_FASTER_WHISPER_VERSION = "1.2.1"
_CTRANSLATE2_PACKAGE = "ctranslate2==4.6.1"
_CTRANSLATE2_VERSION = "4.6.1"
_WHISPER_PACKAGES = (
    _FASTER_WHISPER_PACKAGE,
    _CTRANSLATE2_PACKAGE,
    "av",
    "onnxruntime",
    "tokenizers",
    "huggingface-hub",
    "tqdm",
)
_WHISPER_MODULES = (
    "faster_whisper",
    "ctranslate2",
    "av",
    "onnxruntime",
    "tokenizers",
    "huggingface_hub",
    "tqdm",
)


def _language_code(value: Any) -> str | None:
    language = str(value or "").strip().lower()
    if not language or language in {"auto", "autodetect", "detect"}:
        return None
    return language


class WhisperEngine(BaseEngine, BaseSTTProvider):
    engine_id = "whisper"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        install_python_packages(
            ["faster-whisper"],  # list(_WHISPER_PACKAGES),
            modules=["faster_whisper"],  # list(_WHISPER_MODULES),
            force=True,
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_modules(("faster_whisper", "faster-whisper")),
            ok_message="Whisper engine ready",
            error_message="Whisper engine requires shared state or local dependencies",
        )
        """
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=[
                *cls._missing_modules(
                    ("faster_whisper", _FASTER_WHISPER_PACKAGE),
                    ("ctranslate2", _CTRANSLATE2_PACKAGE),
                    ("av", "av"),
                    ("onnxruntime", "onnxruntime"),
                    ("tokenizers", "tokenizers"),
                    ("huggingface_hub", "huggingface-hub"),
                    ("tqdm", "tqdm"),
                ),
                *cls._missing_chain_versions(),
                *(
                    []
                    if cls._runtime_symbols_available()
                    else ["faster-whisper runtime"]
                ),
            ],
            ok_message="Whisper engine ready",
            error_message="Whisper engine requires shared state or local dependencies",
        )
        """

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
            ("faster-whisper", _FASTER_WHISPER_VERSION, _FASTER_WHISPER_PACKAGE),
            ("ctranslate2", _CTRANSLATE2_VERSION, _CTRANSLATE2_PACKAGE),
        )
        missing: list[str] = []
        for distribution_name, expected_version, label in checks:
            if not cls._package_version_exact(distribution_name, expected_version):
                missing.append(label)
        return missing

    @staticmethod
    def _runtime_symbols_available() -> bool:
        try:
            faster_whisper = importlib.import_module("faster_whisper")
            tokenizer_mod = importlib.import_module("faster_whisper.tokenizer")
            ctranslate2 = importlib.import_module("ctranslate2")
            av = importlib.import_module("av")
            onnxruntime = importlib.import_module("onnxruntime")
            tokenizers = importlib.import_module("tokenizers")
        except Exception:
            return False
        return (
            hasattr(faster_whisper, "WhisperModel")
            and hasattr(tokenizer_mod, "Tokenizer")
            and hasattr(ctranslate2, "get_supported_compute_types")
            and hasattr(av, "open")
            and hasattr(onnxruntime, "get_available_providers")
            and hasattr(tokenizers, "Tokenizer")
        )

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)

        faster_whisper = ensure_import(
            "faster_whisper", dependency_key="faster_whisper"
        )
        tokenizer_mod = ensure_import(
            "faster_whisper.tokenizer", dependency_key="faster_whisper"
        )
        whisper_model = faster_whisper.WhisperModel
        self._Tokenizer = tokenizer_mod.Tokenizer
        device = config.get("device", "auto")
        compute_type = config.get("compute_type", "default")
        model_ref = config.get("model_path") or self.model_name
        if not model_ref:
            raise RuntimeError("whisper_model_required")
        self.model = whisper_model(model_ref, device=device, compute_type=compute_type)

    async def transcribe(self, audio_data: bytes, language: Optional[str] = None):
        def _transcribe():
            audio_file = io.BytesIO(audio_data)
            resolved_language = _language_code(language or self.config.get("language"))
            segments, info = self.model.transcribe(
                audio_file, language=resolved_language, beam_size=5
            )
            full_text = ""
            for segment in segments:
                full_text += segment.text
            return full_text.strip(), info

        text, info = await asyncio.to_thread(_transcribe)
        output_tokens = self._transcription_tokens(text, info.language)
        return {
            "text": text,
            "language": info.language,
            "duration": info.duration,
            "segments": None,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": output_tokens,
                "total_tokens": output_tokens,
            },
            "usage_metadata": {
                "usage_source": "tokenizer",
                "usage_calculation": "engines.whisper.engine.WhisperEngine._transcription_tokens",
            },
        }

    def _transcription_tokens(self, text: str, language: str | None) -> int:
        tokenizer = self._Tokenizer(
            self.model.hf_tokenizer,
            self.model.model.is_multilingual,
            task="transcribe",
            language=language or "en",
        )
        return len(tokenizer.encode(str(text or "")))
