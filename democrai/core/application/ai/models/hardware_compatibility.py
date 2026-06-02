import psutil
from typing import Dict, List, Optional
from pydantic import BaseModel
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.platform.utils.nvml import nvml
from democrai.core.application.ai.engine.manifests import (
    get_provider_definition,
    list_engine_manifests,
    list_provider_definitions,
)
from democrai.core.application.ai.models.catalog import list_engine_models
from democrai.core.runtime.dependencies.installer_env import is_engine_supported


class SystemResources(BaseModel):
    ram_gb: float
    cpu_threads: int
    vram_gb: float = 0.0
    has_gpu: bool = False


class CompatibilityResult(BaseModel):
    is_compatible: bool
    status: str
    details: Dict[str, str]


class HardwareValidator:
    """
    Checks if the local system meets the requirements for running GenAI models.
    """

    def __init__(self):
        self._models_db = self._load_models_db()

    def _load_models_db(self) -> List[dict]:
        flattened: list[dict] = []
        for manifest in list_engine_manifests():
            engine_id = manifest["id"]
            if not engine_id:
                raise ValueError("engine_id is required")
            rows = list_engine_models(engine_id)
            for item in rows:
                flattened.append(item)
        return flattened

    @staticmethod
    def _provider_definition(provider: str) -> dict:
        return get_provider_definition(provider) or {}

    @staticmethod
    def _deployment(provider: str) -> str:
        definition = HardwareValidator._provider_definition(provider)
        return definition.get("deployment", "")

    @staticmethod
    def _kind(provider: str) -> str:
        definition = HardwareValidator._provider_definition(provider)
        return definition.get("kind", "")

    @staticmethod
    def _cpu_fallback_allowed(model_meta: dict) -> bool:
        requirements = model_meta.get("requirements")
        if isinstance(requirements, dict) and "cpu_fallback_allowed" in requirements:
            value = requirements["cpu_fallback_allowed"]
            if not isinstance(value, bool):
                raise ValueError("invalid_cpu_fallback_allowed")
            return value
        metadata = model_meta.get("metadata")
        if isinstance(metadata, dict) and "cpu_fallback_allowed" in metadata:
            value = metadata["cpu_fallback_allowed"]
            if not isinstance(value, bool):
                raise ValueError("invalid_cpu_fallback_allowed")
            return value
        return True

    @staticmethod
    def _partial_gpu_offload_allowed(model_meta: dict) -> bool:
        requirements = model_meta.get("requirements")
        if isinstance(requirements, dict) and "partial_gpu_offload" in requirements:
            value = requirements["partial_gpu_offload"]
            if not isinstance(value, bool):
                raise ValueError("invalid_partial_gpu_offload")
            return value
        metadata = model_meta.get("metadata")
        if isinstance(metadata, dict) and "partial_gpu_offload" in metadata:
            value = metadata["partial_gpu_offload"]
            if not isinstance(value, bool):
                raise ValueError("invalid_partial_gpu_offload")
            return value
        return False

    def get_system_resources(self) -> SystemResources:
        # RAM
        ram_gb = psutil.virtual_memory().total / (1024**3)

        # CPU
        cpu_threads = psutil.cpu_count(logical=True)

        # GPU (VRAM)
        vram_gb = 0.0
        has_gpu = False
        try:
            if nvml is None:
                raise RuntimeError("NVML bindings not available")

            nvml.nvmlInit()
            device_count = nvml.nvmlDeviceGetCount()
            if device_count > 0:
                has_gpu = True
                # Get the sum of VRAM if multiple GPUs, or just the first one?
                # Usually we target the primary GPU
                handle = nvml.nvmlDeviceGetHandleByIndex(0)
                info = nvml.nvmlDeviceGetMemoryInfo(handle)
                vram_gb = info.total / (1024**3)
            nvml.nvmlShutdown()
        except Exception:
            # Fallback if NVML fails or no NVIDIA GPU
            app_ctx().logger.debug("nvml FAIL")

        return SystemResources(
            ram_gb=round(ram_gb, 2),
            cpu_threads=cpu_threads,
            vram_gb=round(vram_gb, 2),
            has_gpu=has_gpu,
        )

    def check_compatibility(self, model_id: str, provider: str) -> CompatibilityResult:
        """
        Validates hardware compatibility for a specific model and provider.
        """
        # Find model metadata
        model_meta = next((m for m in self._models_db if m["id"] == model_id), None)
        if not model_meta:
            return CompatibilityResult(
                is_compatible=False,
                status="unknown_model",
                details={"error": f"Model '{model_id}' not found in database."},
            )

        reqs = model_meta.get("requirements", {})
        res = self.get_system_resources()

        details = {}
        is_compatible = True

        # Check RAM
        min_ram = reqs.get("ram_gb", 0)
        details["ram"] = f"{res.ram_gb:.1f}/{min_ram} GB"
        if res.ram_gb < min_ram:
            is_compatible = False

        # Check CPU
        min_threads = reqs.get("cpu_threads", 0)
        details["cpu"] = f"{res.cpu_threads}/{min_threads} threads"
        if res.cpu_threads < min_threads:
            # CPU is usually a soft requirement, but let's be strict if asked
            pass

        deployment = self._deployment(provider)
        if deployment == "local":
            min_vram = reqs.get("vram_gb", 0)
            details["vram"] = f"{res.vram_gb:.1f}/{min_vram} GB"

            if min_vram > 0:
                if not res.has_gpu:
                    if self._cpu_fallback_allowed(model_meta):
                        details["vram"] += " (No GPU, CPU fallback)"
                    else:
                        is_compatible = False
                        details["vram"] = "GPU required"
                elif res.vram_gb < min_vram:
                    if not self._partial_gpu_offload_allowed(model_meta):
                        is_compatible = False
                    else:
                        details["vram"] += " (Partial GPU offload)"

        status = "ok" if is_compatible else "insufficient_resources"

        return CompatibilityResult(
            is_compatible=is_compatible, status=status, details=details
        )

    def recommend_local_llm_engines(
        self, required_capabilities: Optional[List[str]] = None
    ) -> List[str]:
        resources = self.get_system_resources()
        candidates: list[tuple[int, str]] = []
        for definition in list_provider_definitions(kind="llm"):
            provider_id = definition["id"]
            deployment = definition["deployment"]
            if not provider_id or deployment not in {"local", "hybrid"}:
                continue
            score = 0
            if deployment == "local":
                score += 20
            elif deployment == "hybrid":
                score += 10
            if is_engine_supported(provider_id):
                score += 20
            if resources.has_gpu:
                score += 5
            candidates.append((score, provider_id))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [provider_id for _, provider_id in candidates]
