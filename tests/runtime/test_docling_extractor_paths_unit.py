import sys
from types import ModuleType


def test_docling_cache_paths_are_allowed_by_extractor_sandbox(monkeypatch, tmp_path):
    import democrai.core.application.knowledge.extractor.runtime as runtime_mod
    from democrai.core.infrastructure.sandbox.process_guard import _path_allowed
    from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

    monkeypatch.setattr(runtime_mod, "_extractor_phase_section", lambda *_args: {})
    monkeypatch.setattr(runtime_mod, "get_extractor_local_env_path", lambda _id=None: tmp_path / "env")
    monkeypatch.setattr(runtime_mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")
    monkeypatch.setattr(runtime_mod, "get_extractor_local_config_path", lambda _id=None: tmp_path / "config")
    monkeypatch.setattr(runtime_mod, "get_extractor_local_tmp_path", lambda _id=None: tmp_path / "tmp")
    monkeypatch.setattr(runtime_mod, "get_extractor_venv_path", lambda _id=None: tmp_path / "env" / ".venv")
    monkeypatch.setattr(
        runtime_mod,
        "get_extractor_venv_python_path",
        lambda _id=None: tmp_path / "env" / ".venv" / "Scripts" / "python.exe",
    )
    monkeypatch.setattr(runtime_mod, "extractor_runtime_read_paths", lambda: ())
    monkeypatch.setattr(runtime_mod, "extractor_runtime_system_probe_read_paths", lambda: ())
    monkeypatch.setattr(runtime_mod, "extractor_runtime_dependency_read_paths", lambda: ())
    monkeypatch.setattr(runtime_mod, "extractor_runtime_create_paths", lambda: ())
    monkeypatch.setattr(runtime_mod, "extractor_runtime_modify_paths", lambda: ())

    with process_guard_context(
        subject="docling",
        subject_kind="extractor",
        access=runtime_mod.get_extractor_access("docling", "install"),
        allow_subprocess=True,
        allow_fork=True,
    ):
        targets = (
            tmp_path / "cache" / "docling" / "models" / "repo" / ".cache",
            tmp_path / "cache" / "tessdata" / "eng.traineddata",
        )
        for target in targets:
            assert _path_allowed(str(target), operation="create")
            assert _path_allowed(str(target), operation="modify")
            assert _path_allowed(str(target), operation="read")


def test_docling_paths_are_derived_from_extractor_cache(monkeypatch, tmp_path):
    import extractors.docling.extractor as mod

    monkeypatch.setattr(mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")

    assert mod.DoclingExtractor._cache_root() == tmp_path / "cache"
    assert mod.DoclingExtractor._docling_artifacts_path() == (
        tmp_path / "cache" / "docling" / "models"
    )
    assert mod.DoclingExtractor._tessdata_path() == tmp_path / "cache" / "tessdata"


def test_docling_tesseract_options_receive_explicit_tessdata_path(monkeypatch, tmp_path):
    import extractors.docling.extractor as mod

    captured = {}

    class TesseractOcrOptions:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    docling = ModuleType("docling")
    datamodel = ModuleType("docling.datamodel")
    pipeline_options = ModuleType("docling.datamodel.pipeline_options")
    pipeline_options.TesseractOcrOptions = TesseractOcrOptions

    monkeypatch.setitem(sys.modules, "docling", docling)
    monkeypatch.setitem(sys.modules, "docling.datamodel", datamodel)
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipeline_options)
    monkeypatch.setattr(mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")

    options = mod.DoclingExtractor({"ocr_engine": "tesserocr"})._build_ocr_options()

    assert isinstance(options, TesseractOcrOptions)
    assert captured == {"path": str(tmp_path / "cache" / "tessdata")}


def test_docling_download_models_receives_filesystem_path(monkeypatch, tmp_path):
    import extractors.docling.extractor as mod

    captured = {}

    class ModelDownloader:
        @staticmethod
        def download_models(**kwargs):
            captured.update(kwargs)

    docling = ModuleType("docling")
    utils = ModuleType("docling.utils")
    utils.model_downloader = ModelDownloader

    monkeypatch.setitem(sys.modules, "docling", docling)
    monkeypatch.setitem(sys.modules, "docling.utils", utils)
    monkeypatch.setattr(mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")
    monkeypatch.setattr(mod, "fs_path", lambda path: f"FS::{path}")
    monkeypatch.setattr(mod.os, "makedirs", lambda *_args, **_kwargs: None)

    mod.DoclingExtractor._download_docling_artifacts(ocr_engine="rapidocr")

    assert str(captured["output_dir"]) == f"FS::{tmp_path / 'cache' / 'docling' / 'models'}"
    assert captured["with_rapidocr"] is True
