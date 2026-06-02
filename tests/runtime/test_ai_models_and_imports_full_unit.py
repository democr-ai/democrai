from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "module_name, attrs",
    [
        ("democrai.core.application.ai", ("engine", "models", "model_orchestrator")),
        (
            "democrai.core.application.ai.engine",
            (
                "genai_manager",
                "get_provider_definition",
                "list_provider_definitions",
                "Message",
                "ContentPart",
                "ContentType",
                "CompletionOptions",
                "MessageRole",
            ),
        ),
        (
            "democrai.core.application.ai.models",
            (
                "HardwareValidator",
                "engine_model_source_modes",
                "get_engine_model",
                "list_engine_models",
                "resolve_engine_model",
            ),
        ),
    ],
)
def test_lazy_import_modules_export_attributes(module_name, attrs):
    mod = importlib.import_module(module_name)
    for name in attrs:
        assert getattr(mod, name) is not None
    with pytest.raises(AttributeError):
        getattr(mod, "__missing_symbol__")


def test_base_module_and_provider_contracts():
    base_mod = importlib.import_module("democrai.core.application.ai.engine.base")
    assert base_mod.BaseEngine is not None
    assert base_mod.LLMProvider is not None
    assert base_mod.BaseSTTProvider is not None
    assert base_mod.BaseTTSProvider is not None
    assert base_mod.BaseCvProvider is not None
    with pytest.raises(AttributeError):
        getattr(base_mod, "Nope")

    audio_mod = importlib.import_module("democrai.core.application.ai.engine.base.audio")
    cv_mod = importlib.import_module("democrai.core.application.ai.engine.base.cv")
    llm_mod = importlib.import_module("democrai.core.application.ai.engine.base.llm")

    class _STT(audio_mod.BaseSTTProvider):
        async def transcribe(self, audio_data: bytes, language=None):
            return {"size": len(audio_data), "language": language}

    class _TTS(audio_mod.BaseTTSProvider):
        async def synthesize(self, text, options):
            return {"text": text, "options": options}

        async def synthesize_stream(self, text, options):
            yield b"x"

    class _CV(cv_mod.BaseCvProvider):
        def detect(self, *_a, **_k):
            return {"ok": True}

        async def get_detections(self, *_a, **_k):
            return []

    class _LLM(llm_mod.LLMProvider):
        async def _generate_completion(self, messages, options):
            return {"messages": messages, "options": options}

        async def _generate_stream(self, messages, options):
            yield {"chunk": True}

    stt = _STT({"model": "m1", "model_revision": "r1"})
    tts = _TTS({"model": "m2", "model_revision": "r2"})
    cv = _CV({"model": "m3", "model_revision": "r3"})
    assert stt.model_name == "m1" and tts.model_revision == "r2" and cv.model_name == "m3"

    llm = _LLM()
    with pytest.raises(NotImplementedError):
        __import__("asyncio").run(llm.embed_texts(["a"]))
    with pytest.raises(NotImplementedError):
        __import__("asyncio").run(llm.download_model("m"))
    info = llm.get_info()
    assert info["provider"] == "_LLM"


def test_selection_policy_remaining_branches(monkeypatch):
    sp_mod = importlib.import_module("democrai.core.application.ai.models.selection_policy")

    monkeypatch.setattr(sp_mod, "get_provider_definition", lambda name: {"deployment": "remote", "kind": "llm"} if name == "x" else None)
    assert sp_mod._provider_deployment("x") == "remote"
    assert sp_mod._provider_deployment("missing") == ""

    assert sp_mod.annotate_provider(None, model_info=SimpleNamespace(provider="x")) is None

    class _P:
        pass

    class _Bad:
        def __setattr__(self, *_a, **_k):
            raise RuntimeError("nope")

    p = _P()
    p.real_provider = _Bad()
    out = sp_mod.annotate_provider(p, model_info=SimpleNamespace(provider="x", name="m"), engine_name=None)
    assert out is p

    assert sp_mod.provider_capabilities(SimpleNamespace(capabilities=None)) == set()
    assert sp_mod.is_local_provider("x") is False

    assert sp_mod.effective_policy_mode({"objective_overrides": {"chat": {"deployment": "local"}}}, objective="chat", prefer_local=None) == "local"
    assert sp_mod.effective_policy_mode({"objective_overrides": []}, objective="chat", prefer_local=None) == "hybrid"

    hv = SimpleNamespace(recommend_local_llm_engines=lambda **_k: ["a"])
    monkeypatch.setattr(sp_mod, "_provider_deployment", lambda p: "hybrid" if p == "h" else "")
    assert sp_mod.engine_fit_score("h", {"chat"}, hardware_validator=hv) == 8
    assert sp_mod.engine_fit_score("z", {"chat"}, hardware_validator=hv) == 0


def test_storage_module_paths(tmp_path: Path):
    storage_mod = importlib.import_module("democrai.core.application.ai.models.storage")

    assert storage_mod.MODEL_STORAGE_ROOT == "models"

    with pytest.raises(ValueError, match="Model paths must be stored under models/"):
        storage_mod.normalize_model_storage_path("media/models/a.bin")
    assert storage_mod.normalize_model_storage_path("models/a.bin") == "models/a.bin"
    assert storage_mod.normalize_model_storage_path("a.bin") == "models/a.bin"
    with pytest.raises(ValueError, match="Missing model path"):
        storage_mod.normalize_model_storage_path(" ")
    with pytest.raises(ValueError, match="storage-relative"):
        storage_mod.normalize_model_storage_path(str((tmp_path / "a.bin").resolve()))
    assert (
        storage_mod.normalize_model_storage_path("other/models/a.bin")
        == "models/other/models/a.bin"
    )


def test_catalog_module_full_paths(monkeypatch, tmp_path: Path):
    cat_mod = importlib.import_module("democrai.core.application.ai.models.catalog")

    assert cat_mod._verify_engine_id("e1") == "e1"
    assert cat_mod._verify_model_id("m1") == "m1"
    with pytest.raises(ValueError, match="engine_id is required"):
        cat_mod._verify_engine_id("")
    with pytest.raises(ValueError, match="model_id is required"):
        cat_mod._verify_model_id("")

    monkeypatch.setattr(cat_mod, "get_engine_roots", lambda: (tmp_path,))
    with pytest.raises(ValueError, match="engine_id is required"):
        cat_mod._engine_dir("")
    assert cat_mod._engine_dir("e1") == tmp_path / "e1"

    with pytest.raises(ValueError, match="json_file_not_found"):
        cat_mod._load_json(tmp_path / "missing.json")

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_json"):
        cat_mod._load_json(bad_json)

    arr_json = tmp_path / "arr.json"
    arr_json.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_json_object"):
        cat_mod._load_json(arr_json)

    valid_json = tmp_path / "ok.json"
    valid_json.write_text('{"x":1}', encoding="utf-8")
    assert cat_mod._load_json(valid_json)["x"] == 1

    monkeypatch.setattr(cat_mod, "get_engine_manifest", lambda eid: None)
    with pytest.raises(ValueError, match="engine_manifest_not_found"):
        cat_mod._engine_manifest("e1")

    manifest = {
        "id": "e1",
        "models": {
            "source_modes": ["catalog", "definition", "catalog", "artifact"],
            "custom_definition": {"enabled": True, "schema": "schemas/definition.json"},
            "artifact_upload": {"enabled": True, "schema": "schemas/artifact.json"},
            "catalog": {"enabled": True, "path": "catalog/models.json"},
        },
    }
    monkeypatch.setattr(cat_mod, "get_engine_manifest", lambda eid: manifest if eid == "e1" else None)

    (tmp_path / "e1" / "schemas").mkdir(parents=True, exist_ok=True)
    (tmp_path / "e1" / "schemas" / "definition.json").write_text('{"kind":"def"}', encoding="utf-8")
    (tmp_path / "e1" / "schemas" / "artifact.json").write_text('{"kind":"art"}', encoding="utf-8")
    (tmp_path / "e1" / "catalog").mkdir(parents=True, exist_ok=True)
    (tmp_path / "e1" / "catalog" / "models.json").write_text(
        json.dumps({"engine_id": "e1", "models": [{"id": "m1", "capabilities": ["chat"], "interfaces": [], "runtime": {}}]}),
        encoding="utf-8",
    )

    assert cat_mod.engine_model_source_modes("e1") == ["catalog", "definition", "artifact"]
    mgmt = cat_mod.get_engine_model_management("e1")
    assert mgmt["engine_id"] == "e1"
    assert cat_mod.get_engine_model_schema("e1", source_mode="definition")["kind"] == "def"
    assert cat_mod.get_engine_model_schema("e1", source_mode="artifact")["kind"] == "art"
    with pytest.raises(ValueError, match="unsupported_model_schema_mode"):
        cat_mod.get_engine_model_schema("e1", source_mode="other")

    manifest_disabled = {"id": "e1", "models": {"custom_definition": {"enabled": False}}}
    monkeypatch.setattr(cat_mod, "get_engine_manifest", lambda eid: manifest_disabled)
    with pytest.raises(ValueError, match="model_schema_disabled"):
        cat_mod.get_engine_model_schema("e1", source_mode="definition")

    monkeypatch.setattr(cat_mod, "get_engine_manifest", lambda eid: manifest)
    assert cat_mod._catalog_path("e1") is not None

    mismatch = tmp_path / "e1" / "catalog" / "models.json"
    mismatch.write_text(json.dumps({"engine_id": "e2", "models": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="engine_model_catalog_mismatch"):
        cat_mod._catalog_payload("e1")

    mismatch.write_text(json.dumps({"engine_id": "e1", "models": [{"id": "m1", "capabilities": ["chat"], "interfaces": [], "runtime": {}}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="model_id is required"):
        cat_mod._prepare_runtime_definition("e1", {}, source_mode="catalog")
    with pytest.raises(ValueError, match="engine_id mismatch"):
        cat_mod._prepare_runtime_definition("e1", {"id": "m", "engine_id": "x", "capabilities": [], "interfaces": [], "runtime": {}}, source_mode="catalog")
    with pytest.raises(ValueError, match="capabilities must be a list"):
        cat_mod._prepare_runtime_definition("e1", {"id": "m", "capabilities": "bad", "interfaces": [], "runtime": {}}, source_mode="catalog")
    with pytest.raises(ValueError, match="interfaces must be a list"):
        cat_mod._prepare_runtime_definition("e1", {"id": "m", "capabilities": [], "interfaces": "bad", "runtime": {}}, source_mode="catalog")
    with pytest.raises(ValueError, match="runtime must be an object"):
        cat_mod._prepare_runtime_definition("e1", {"id": "m", "capabilities": [], "interfaces": [], "runtime": "bad"}, source_mode="catalog")

    prepared = cat_mod._prepare_runtime_definition("e1", {"id": "m2", "capabilities": [], "interfaces": [], "runtime": {}}, source_mode="definition")
    assert prepared["provisioning"]["mode"] == "definition"
    assert prepared["runtime"]["execution_mode"] == "standard"

    rows = cat_mod.list_engine_models("e1")
    assert len(rows) == 1 and rows[0]["id"] == "m1"
    assert cat_mod.get_engine_model("e1", "m1")["id"] == "m1"
    with pytest.raises(ValueError, match="model_id is required"):
        cat_mod.get_engine_model("e1", "")

    with pytest.raises(ValueError, match="unsupported_model_source_mode"):
        cat_mod.resolve_engine_model("e1", source_mode="other")
    with pytest.raises(ValueError, match="model_id is required for catalog resolution"):
        cat_mod.resolve_engine_model("e1", source_mode="catalog", model_id=None)
    with pytest.raises(ValueError, match="engine_model_not_found"):
        cat_mod.resolve_engine_model("e1", source_mode="catalog", model_id="missing")

    catalog_model = cat_mod.resolve_engine_model("e1", source_mode="catalog", model_id="m1")
    assert catalog_model["source_mode"] == "catalog"

    with pytest.raises(ValueError, match="definition payload is required"):
        cat_mod.resolve_engine_model("e1", source_mode="definition", definition=None)

    definition_model = cat_mod.resolve_engine_model("e1", source_mode="definition", definition={"id": "d1", "capabilities": [], "interfaces": [], "runtime": {}})
    assert definition_model["source_mode"] == "definition"

    with pytest.raises(ValueError, match="artifact payload is required"):
        cat_mod.resolve_engine_model("e1", source_mode="artifact", model_id="a1", artifact={})

    artifact_model = cat_mod.resolve_engine_model(
        "e1",
        source_mode="artifact",
        model_id="a1",
        definition={"capabilities": [], "interfaces": [], "runtime": {}},
        artifact={"uploaded_artifact": {"path": "media/x"}},
    )
    assert artifact_model["source_mode"] == "artifact"
    assert artifact_model["runtime"]["artifact_ref"] == "uploaded_artifact"


def test_hardware_compatibility_module(monkeypatch):
    hw_mod = importlib.import_module("democrai.core.application.ai.models.hardware_compatibility")

    monkeypatch.setattr(hw_mod, "list_engine_manifests", lambda: [{"id": "e1"}])
    monkeypatch.setattr(hw_mod, "list_engine_models", lambda engine_id: [{"id": "m1"}])
    monkeypatch.setattr(hw_mod, "get_provider_definition", lambda provider: {"deployment": "local", "kind": "llm"} if provider == "p1" else {})

    validator = hw_mod.HardwareValidator()
    assert validator._models_db == [{"id": "m1"}]
    monkeypatch.setattr(hw_mod, "list_engine_manifests", lambda: [{"id": ""}])
    with pytest.raises(ValueError, match="engine_id is required"):
        hw_mod.HardwareValidator()
    monkeypatch.setattr(hw_mod, "list_engine_manifests", lambda: [{"id": "e1"}])
    assert validator._deployment("p1") == "local"
    assert validator._kind("p1") == "llm"

    assert validator._cpu_fallback_allowed({"requirements": {"cpu_fallback_allowed": False}}) is False
    assert validator._cpu_fallback_allowed({"metadata": {"cpu_fallback_allowed": True}}) is True
    assert validator._cpu_fallback_allowed({}) is True
    assert validator._partial_gpu_offload_allowed({"requirements": {"partial_gpu_offload": True}}) is True
    assert validator._partial_gpu_offload_allowed({"metadata": {"partial_gpu_offload": True}}) is True
    assert validator._partial_gpu_offload_allowed({}) is False

    monkeypatch.setattr(hw_mod.psutil, "virtual_memory", lambda: SimpleNamespace(total=16 * 1024**3))
    monkeypatch.setattr(hw_mod.psutil, "cpu_count", lambda logical=True: 8)
    monkeypatch.setattr(hw_mod, "nvml", None)
    monkeypatch.setattr(hw_mod, "app_ctx", lambda: SimpleNamespace(logger=SimpleNamespace(debug=lambda *_a, **_k: None)))
    res = validator.get_system_resources()
    assert res.ram_gb == 16.0 and res.has_gpu is False

    class _NVML:
        def nvmlInit(self):
            return None

        def nvmlDeviceGetCount(self):
            return 1

        def nvmlDeviceGetHandleByIndex(self, _i):
            return "h"

        def nvmlDeviceGetMemoryInfo(self, _h):
            return SimpleNamespace(total=8 * 1024**3)

        def nvmlShutdown(self):
            return None

    monkeypatch.setattr(hw_mod, "nvml", _NVML())
    res_gpu = validator.get_system_resources()
    assert res_gpu.has_gpu is True and res_gpu.vram_gb == 8.0

    validator._models_db = [{"id": "m1", "requirements": {"ram_gb": 1, "cpu_threads": 1, "vram_gb": 2}}]
    monkeypatch.setattr(validator, "get_system_resources", lambda: hw_mod.SystemResources(ram_gb=16.0, cpu_threads=8, vram_gb=0.0, has_gpu=False))
    monkeypatch.setattr(validator, "_deployment", lambda provider: "local")
    ok = validator.check_compatibility("m1", "p1")
    assert ok.is_compatible is True and "CPU fallback" in ok.details["vram"]

    validator._models_db = [{"id": "m2", "requirements": {"ram_gb": 1, "cpu_threads": 1, "vram_gb": 6, "cpu_fallback_allowed": False}}]
    bad = validator.check_compatibility("m2", "p1")
    assert bad.is_compatible is False

    validator._models_db = [{"id": "m3", "requirements": {"ram_gb": 1, "cpu_threads": 1, "vram_gb": 16, "partial_gpu_offload": True}}]
    monkeypatch.setattr(validator, "get_system_resources", lambda: hw_mod.SystemResources(ram_gb=16.0, cpu_threads=8, vram_gb=8.0, has_gpu=True))
    partial = validator.check_compatibility("m3", "p1")
    assert partial.is_compatible is True and "Partial GPU offload" in partial.details["vram"]

    unknown = validator.check_compatibility("missing", "p1")
    assert unknown.status == "unknown_model"

    monkeypatch.setattr(hw_mod, "list_provider_definitions", lambda kind=None: [{"id": "locala", "deployment": "local"}, {"id": "hyb", "deployment": "hybrid"}, {"id": "rem", "deployment": "remote"}, {"id": "", "deployment": "local"}])
    monkeypatch.setattr(hw_mod, "is_engine_supported", lambda provider_id: provider_id == "locala")
    monkeypatch.setattr(validator, "get_system_resources", lambda: hw_mod.SystemResources(ram_gb=16.0, cpu_threads=8, vram_gb=8.0, has_gpu=True))
    rec = validator.recommend_local_llm_engines(required_capabilities=["chat"])
    assert rec == ["locala", "hyb"]
