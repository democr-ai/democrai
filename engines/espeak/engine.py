import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, AsyncGenerator

from democrai.sdk.engines import BaseEngine, BaseTTSProvider


class EspeakEngine(BaseEngine, BaseTTSProvider):
    engine_id = "espeak"

    @classmethod
    def _resolve_espeak_binary(cls) -> str:
        search_dirs = {
            "linux": (
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
            ),
            "darwin": (
                "/opt/homebrew/bin",
                "/opt/local/bin",
                "/usr/local/bin",
            ),
        }.get(sys.platform, ())
        for command_name in ("espeak-ng", "espeak"):
            for base_dir in search_dirs:
                candidate = Path(base_dir) / command_name
                try:
                    if (
                        candidate.exists()
                        and candidate.is_file()
                        and os.access(candidate, os.X_OK)
                    ):
                        return str(candidate)
                except PermissionError:
                    continue
        raise RuntimeError("eSpeak executable not found (expected espeak-ng or espeak)")

    @classmethod
    def _check_supported(cls, env: dict | None = None) -> dict[str, Any]:
        del env
        try:
            cls._resolve_espeak_binary()
            return cls._build_supported_payload(supported=True)
        except Exception:
            return cls._build_supported_payload(
                supported=False,
                reason="eSpeak requires an available espeak-ng or espeak executable",
            )

    @classmethod
    def is_supported(cls, env: dict | None = None) -> bool:
        del env
        try:
            cls._resolve_espeak_binary()
            return True
        except Exception:
            return False

    @classmethod
    def unsupported_reason(cls, env: dict | None = None) -> str:
        del env
        return "eSpeak requires an available espeak-ng or espeak executable"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        del force
        cls._resolve_espeak_binary()

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        try:
            cls._resolve_espeak_binary()
            missing_local: list[str] = []
        except RuntimeError:
            missing_local = ["espeak"]
        missing_shared: list[str] = []
        return cls._build_ready_payload(
            missing_shared=missing_shared,
            missing_local=missing_local,
            ok_message="eSpeak engine ready",
            error_message="eSpeak engine requires shared state or local executable",
        )

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)
        self.binary = self._resolve_espeak_binary()
        self.default_voice = str(config.get("voice") or self.model_name or "en-us")
        self.default_wpm = int(config.get("wpm") or 175)
        self.default_pitch = int(config.get("pitch") or 50)
        self.default_amplitude = int(config.get("amplitude") or 100)
        self.default_word_gap = int(config.get("word_gap") or 0)

    async def synthesize(self, text: str, options: Any):
        voice = str(options.voice or self.default_voice)
        wpm = max(80, min(500, int(getattr(options, "wpm", None) or self.default_wpm)))
        pitch = max(0, min(99, int(getattr(options, "pitch", None) or self.default_pitch)))
        amplitude = max(
            0,
            min(200, int(getattr(options, "amplitude", None) or self.default_amplitude)),
        )
        word_gap = max(0, int(getattr(options, "word_gap", None) or self.default_word_gap))

        def _run() -> bytes:
            cmd = [
                self.binary,
                "-v",
                voice,
                "-s",
                str(wpm),
                "-p",
                str(pitch),
                "-a",
                str(amplitude),
            ]
            if word_gap:
                cmd.extend(["-g", str(word_gap)])
            cmd.extend(
                [
                    "--stdout",
                    str(text or ""),
                ]
            )
            proc = subprocess.run(cmd, check=True, capture_output=True)  # nosec B603
            return bytes(proc.stdout or b"")

        wav_data = await asyncio.to_thread(_run)
        return {
            "data": wav_data,
            "content_type": "audio/wav",
            "usage_metadata": {
                "usage_source": "calculated",
                "usage_calculation": "runtime.invocation.text_regex_tokens_plus_audio_seconds_x_50",
            },
        }

    async def synthesize_stream(
        self, text: str, options: Any
    ) -> AsyncGenerator[bytes, None]:
        resp = await self.synthesize(text, options)
        yield resp["data"]
