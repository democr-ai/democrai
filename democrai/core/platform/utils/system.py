import psutil
from typing import Dict, Any
import atexit
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.platform.utils.nvml import nvml


def _decode_nvml_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    if value is None:
        return ""
    return str(value).strip()


def _cuda_driver_version_from_raw(value: Any) -> str:
    try:
        raw = int(value)
    except Exception:
        return ""
    if raw <= 0:
        return ""
    major = raw // 1000
    minor = (raw % 1000) // 10
    return f"{major}.{minor}"


class SystemResourceMonitor:
    """
    Monitors system resources (RAM, VRAM) to assist in model orchestration.
    """

    def __init__(self):
        self._nvml_initialized = False
        try:
            if nvml is None:
                return
            nvml.nvmlInit()
            self._nvml_initialized = True
        except Exception as e:
            # NVML might fail if no NVIDIA GPU or drivers are present
            app_ctx().logger.warning(f"[Monitor] NVML initialization failed: {e}")

    def get_free_ram_mb(self) -> int:
        """Returns free system RAM in Megabytes."""
        return int(psutil.virtual_memory().available / (1024 * 1024))

    def get_total_ram_mb(self) -> int:
        """Returns total system RAM in Megabytes."""
        return int(psutil.virtual_memory().total / (1024 * 1024))

    def get_free_vram_mb(self) -> int:
        """Returns free VRAM in Megabytes (across all NVIDIA GPUs)."""
        if not self._nvml_initialized:
            return 0

        try:
            device_count = nvml.nvmlDeviceGetCount()
            total_free = 0
            for i in range(device_count):
                handle = nvml.nvmlDeviceGetHandleByIndex(i)
                info = nvml.nvmlDeviceGetMemoryInfo(handle)
                total_free += info.free
            return int(total_free / (1024 * 1024))
        except Exception as e:
            app_ctx().logger.warning(f"[Monitor] Error getting VRAM info: {e}")
            return 0

    def get_total_vram_mb(self) -> int:
        """Returns total VRAM in Megabytes (across all NVIDIA GPUs)."""
        if not self._nvml_initialized:
            return 0

        try:
            device_count = nvml.nvmlDeviceGetCount()
            total_vram = 0
            for i in range(device_count):
                handle = nvml.nvmlDeviceGetHandleByIndex(i)
                info = nvml.nvmlDeviceGetMemoryInfo(handle)
                total_vram += info.total
            return int(total_vram / (1024 * 1024))
        except Exception as e:
            app_ctx().logger.warning(f"[Monitor] Error getting total VRAM info: {e}")
            return 0

    def get_nvidia_driver_version(self) -> str:
        """Returns the NVIDIA driver version reported by NVML."""
        if not self._nvml_initialized:
            return ""
        try:
            return _decode_nvml_text(nvml.nvmlSystemGetDriverVersion())
        except Exception as e:
            app_ctx().logger.warning(f"[Monitor] Error getting NVIDIA driver version: {e}")
            return ""

    def get_cuda_driver_version(self) -> str:
        """Returns the CUDA driver API version reported by NVML."""
        if not self._nvml_initialized:
            return ""
        for name in (
            "nvmlSystemGetCudaDriverVersion_v2",
            "nvmlSystemGetCudaDriverVersion",
        ):
            getter = getattr(nvml, name, None)
            if not callable(getter):
                continue
            try:
                resolved = _cuda_driver_version_from_raw(getter())
                if resolved:
                    return resolved
            except Exception:
                continue
        return ""

    def get_resources(self) -> Dict[str, Any]:
        """Returns a summary of available resources."""
        total_vram_mb = self.get_total_vram_mb()
        free_vram_mb = self.get_free_vram_mb()
        return {
            "ram_free_mb": self.get_free_ram_mb(),
            "ram_total_mb": self.get_total_ram_mb(),
            "vram_free_mb": free_vram_mb,
            "vram_total_mb": total_vram_mb,
            "has_nvidia_gpu": self._nvml_initialized,
            "nvidia_driver_version": self.get_nvidia_driver_version(),
            "cuda_driver_version": self.get_cuda_driver_version(),
        }

    def shutdown(self):
        """Shutdown NVML explicitly to prevent segfaults on exit."""
        if self._nvml_initialized:
            try:
                nvml.nvmlShutdown()
                self._nvml_initialized = False
                
                # Safely attempt to log (might fail during atexit cleanup)
                try:
                    ctx = app_ctx()
                    if ctx and hasattr(ctx, "logger") and ctx.logger:
                        ctx.logger.info("[Monitor] NVML shutdown successful")
                except Exception:
                    pass
            except Exception as e:
                # Use print as fallback if logger is gone
                print(f"[Monitor] NVML shutdown failed: {e}")


_resource_monitor: SystemResourceMonitor | None = None


def get_resource_monitor() -> SystemResourceMonitor:
    global _resource_monitor
    if _resource_monitor is None:
        _resource_monitor = SystemResourceMonitor()
    return _resource_monitor


def shutdown_resource_monitor() -> None:
    global _resource_monitor
    if _resource_monitor is not None:
        _resource_monitor.shutdown()
        _resource_monitor = None


atexit.register(shutdown_resource_monitor)
