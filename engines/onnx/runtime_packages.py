from __future__ import annotations

from dataclasses import dataclass


ORT_CUDA_11_INDEX = (
    "https://aiinfra.pkgs.visualstudio.com/PublicPackages/"
    "_packaging/onnxruntime-cuda-11/pypi/simple/"
)
ORT_CPU_PACKAGE = "onnxruntime==1.20.1"
ORT_CUDA_12_PACKAGE = "onnxruntime-gpu==1.20.1"
ORT_CUDA_11_PACKAGE = "onnxruntime-gpu==1.20.1"


@dataclass(frozen=True)
class OnnxRuntimePackagePlan:
    profile: str
    package: str
    optimum_extra: str
    index_url: str | None = None
    pre: bool = False


def resolve_onnx_runtime_package_plan(
    *,
    torch_profile: str,
    os_name: str,
) -> OnnxRuntimePackagePlan:
    normalized_os = str(os_name or "").strip().lower()
    profile = str(torch_profile or "").strip().lower()

    if normalized_os == "darwin" or profile == "cpu":
        return OnnxRuntimePackagePlan("cpu", ORT_CPU_PACKAGE, "onnxruntime")
    if normalized_os not in {"linux", "windows"}:
        return OnnxRuntimePackagePlan("cpu", ORT_CPU_PACKAGE, "onnxruntime")
    if profile == "cu130":
        return OnnxRuntimePackagePlan(
            "cpu",
            ORT_CPU_PACKAGE,
            "onnxruntime",
        )
    if profile in {"cu128", "cu126", "cu124", "cu121"}:
        return OnnxRuntimePackagePlan(
            "cu12x",
            ORT_CUDA_12_PACKAGE,
            "onnxruntime-gpu",
        )
    if profile == "cu118":
        return OnnxRuntimePackagePlan(
            "cu118",
            ORT_CUDA_11_PACKAGE,
            "onnxruntime-gpu",
            index_url=ORT_CUDA_11_INDEX,
        )
    return OnnxRuntimePackagePlan("cpu", ORT_CPU_PACKAGE, "onnxruntime")
