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
    assert kwargs["force"] is True
    assert kwargs["extra_index_url"] == "https://download.pytorch.org/whl/cpu"
    assert kwargs["extra_pip_args"] == ["--constraint", "/tmp/torch-constraints.txt"]
    assert len(calls) == 1


def test_onnx_install_packages_keep_cpu_runtime_on_macos():
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])

    packages = engine_mod.OnnxEngine._install_packages("cu128", os_name="Darwin")

    assert "optimum-onnx[onnxruntime]==0.1.0" in packages
    assert "onnxruntime" in packages
    assert "onnxruntime-gpu" not in packages


def test_onnx_install_packages_use_gpu_runtime_on_windows_cuda_profile():
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])

    packages = engine_mod.OnnxEngine._install_packages("cu128", os_name="Windows")

    assert "optimum-onnx[onnxruntime-gpu]==0.1.0" in packages
    assert "onnxruntime-gpu" in packages


def test_onnx_missing_labels_validate_runtime_imports_without_exporter(monkeypatch):
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])
    imported = []

    monkeypatch.setattr(
        engine_mod.importlib.util,
        "find_spec",
        lambda _name: object(),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_transformers_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_huggingface_hub_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_optimum_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_optimum_onnx_version_supported",
        classmethod(lambda cls: True),
    )

    def _import_module(name):
        imported.append(name)
        if name == "optimum.exporters.onnx":
            raise AssertionError("exporter import must not be used for ONNX readiness")
        if name == "optimum.onnxruntime":
            return SimpleNamespace(
                ORTModelForCausalLM=object(),
                ORTModelForFeatureExtraction=object(),
                ORTModelForSequenceClassification=object(),
                ORTModelForTokenClassification=object(),
            )
        if name == "transformers":
            return SimpleNamespace(
                AutoTokenizer=object(),
                TextIteratorStreamer=object(),
            )
        if name == "sentence_transformers":
            return SimpleNamespace(CrossEncoder=object())
        raise AssertionError(name)

    monkeypatch.setattr(engine_mod.importlib, "import_module", _import_module)
    monkeypatch.setattr(engine_mod, "torch_runtime_matches_plan", lambda: True)

    assert engine_mod.OnnxEngine._missing_module_labels() == []
    assert "optimum.onnxruntime" in imported
    assert "transformers" in imported
    assert "sentence_transformers" in imported
    assert "optimum.exporters.onnx" not in imported


def test_onnx_missing_labels_include_broken_runtime_import(monkeypatch):
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])

    monkeypatch.setattr(
        engine_mod.importlib.util,
        "find_spec",
        lambda _name: object(),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_transformers_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_huggingface_hub_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_optimum_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_optimum_onnx_version_supported",
        classmethod(lambda cls: True),
    )

    def _import_module(name):
        if name == "optimum.onnxruntime":
            raise RuntimeError("broken onnxruntime import")
        if name == "transformers":
            return SimpleNamespace(
                AutoTokenizer=object(),
                TextIteratorStreamer=object(),
            )
        if name == "sentence_transformers":
            return SimpleNamespace(CrossEncoder=object())
        raise AssertionError(name)

    monkeypatch.setattr(engine_mod.importlib, "import_module", _import_module)
    monkeypatch.setattr(engine_mod, "torch_runtime_matches_plan", lambda: True)

    assert (
        "optimum-onnx[onnxruntime]==0.1.0"
        in engine_mod.OnnxEngine._missing_module_labels()
    )


def test_onnx_missing_labels_handles_missing_optimum_parent(monkeypatch):
    engine_mod = __import__("engines.onnx.engine", fromlist=["OnnxEngine"])

    def _find_spec(name):
        if name == "optimum.onnxruntime":
            raise ModuleNotFoundError("No module named 'optimum'")
        return object()

    monkeypatch.setattr(engine_mod.importlib.util, "find_spec", _find_spec)
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_transformers_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_transformers_runtime_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_sentence_transformers_runtime_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_huggingface_hub_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_optimum_version_supported",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(
        engine_mod.OnnxEngine,
        "_optimum_onnx_version_supported",
        classmethod(lambda cls: True),
    )

    assert (
        "optimum-onnx[onnxruntime]==0.1.0"
        in engine_mod.OnnxEngine._missing_module_labels()
    )


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
