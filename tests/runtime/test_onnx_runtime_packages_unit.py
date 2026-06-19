from __future__ import annotations

from engines.onnx.runtime_packages import (
    ORT_CPU_PACKAGE,
    ORT_CUDA_11_INDEX,
    ORT_CUDA_11_PACKAGE,
    ORT_CUDA_12_PACKAGE,
    resolve_onnx_runtime_package_plan,
)


def test_onnx_runtime_plan_uses_cpu_package_for_cpu_profile():
    plan = resolve_onnx_runtime_package_plan(torch_profile="cpu", os_name="Linux")

    assert plan.profile == "cpu"
    assert plan.package == ORT_CPU_PACKAGE
    assert plan.optimum_extra == "onnxruntime"
    assert plan.index_url is None
    assert plan.pre is False


def test_onnx_runtime_plan_uses_cpu_package_on_macos():
    plan = resolve_onnx_runtime_package_plan(torch_profile="cu128", os_name="Darwin")

    assert plan.profile == "cpu"
    assert plan.package == ORT_CPU_PACKAGE
    assert plan.optimum_extra == "onnxruntime"


def test_onnx_runtime_plan_uses_pinned_gpu_package_for_cuda_12_profiles():
    for profile in ("cu128", "cu126", "cu124", "cu121"):
        plan = resolve_onnx_runtime_package_plan(torch_profile=profile, os_name="Linux")

        assert plan.profile == "cu12x"
        assert plan.package == ORT_CUDA_12_PACKAGE
        assert plan.optimum_extra == "onnxruntime-gpu"
        assert plan.index_url is None
        assert plan.pre is False


def test_onnx_runtime_plan_falls_back_to_cpu_for_cuda_13_profile():
    plan = resolve_onnx_runtime_package_plan(torch_profile="cu130", os_name="Linux")

    assert plan.profile == "cpu"
    assert plan.package == ORT_CPU_PACKAGE
    assert plan.optimum_extra == "onnxruntime"
    assert plan.index_url is None
    assert plan.pre is False


def test_onnx_runtime_plan_uses_cuda_11_feed_for_cuda_118_profile():
    plan = resolve_onnx_runtime_package_plan(torch_profile="cu118", os_name="Linux")

    assert plan.profile == "cu118"
    assert plan.package == ORT_CUDA_11_PACKAGE
    assert plan.optimum_extra == "onnxruntime-gpu"
    assert plan.index_url == ORT_CUDA_11_INDEX
    assert plan.pre is False
