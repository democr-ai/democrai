from __future__ import annotations

from types import SimpleNamespace


def test_onnx_install_uses_compatible_optimum_transformers_packages(monkeypatch):
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])
    calls = []

    monkeypatch.setattr(
        engine_mod,
        "install_torch_runtime",
        lambda force=False: SimpleNamespace(
            profile="cpu",
            index_url="https://download.pytorch.org/whl/cpu",
        ),
    )
    monkeypatch.setattr(
        engine_mod,
        "write_installed_torch_constraint",
        lambda: "/tmp/torch-constraints.txt",
    )
    monkeypatch.setattr(
        engine_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)),
    )

    engine_mod.OnnxEngine._install(force=True)

    assert calls
    packages, kwargs = calls[0]
    assert "optimum==2.1.0" in packages
    assert "optimum-onnx[onnxruntime]==0.1.0" in packages
    assert "transformers>=4.36,<4.58" in packages
    assert "onnxruntime" in packages
    assert "optimum" not in packages
    assert "transformers" not in packages
    assert kwargs["modules"] == [
        "diffusers",
        "optimum.onnxruntime",
        "sentence_transformers",
        "transformers",
    ]
    assert kwargs["extra_index_url"] == "https://download.pytorch.org/whl/cpu"
    assert kwargs["extra_pip_args"] == ["--constraint", "/tmp/torch-constraints.txt"]


def test_onnx_install_packages_use_gpu_optimum_extra_for_cuda_profile():
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])

    packages = engine_mod.OnnxEngine._install_packages("cu128")

    assert "optimum-onnx[onnxruntime-gpu]==0.1.0" in packages
    assert "onnxruntime-gpu" in packages


def test_onnx_missing_labels_include_broken_optimum_exporter(monkeypatch):
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])

    monkeypatch.setattr(
        engine_mod.importlib.util,
        "find_spec",
        lambda _name: object(),
    )
    monkeypatch.setattr(engine_mod.OnnxEngine, "_optimum_onnx_export_supported", classmethod(lambda cls: False))
    monkeypatch.setattr(engine_mod.OnnxEngine, "_transformers_version_supported", classmethod(lambda cls: True))
    monkeypatch.setattr(engine_mod.OnnxEngine, "_huggingface_hub_version_supported", classmethod(lambda cls: True))
    monkeypatch.setattr(engine_mod, "torch_runtime_matches_plan", lambda: True)

    assert "optimum-onnx[onnxruntime]==0.1.0" in engine_mod.OnnxEngine._missing_module_labels()


def test_onnx_transformers_version_range(monkeypatch):
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])
    versions = {"transformers": "4.57.6"}

    monkeypatch.setattr(
        engine_mod.importlib.metadata,
        "version",
        lambda name: versions[name],
    )
    assert engine_mod.OnnxEngine._transformers_version_supported() is True

    versions["transformers"] = "5.9.0"
    assert engine_mod.OnnxEngine._transformers_version_supported() is False
