from __future__ import annotations

from types import SimpleNamespace

from engines.nvidia_nim import engine as nim_engine
from engines.install.nvidia_nim import install_common


def test_engine_install_uses_pinned_requests(monkeypatch):
    calls = []

    def fake_install(packages, *, modules, force):
        calls.append({"packages": packages, "modules": modules, "force": force})
        return True

    monkeypatch.setattr(nim_engine, "install_python_packages", fake_install)

    nim_engine.NvidiaNimEngine._install(force=True)

    assert calls == [
        {
            "packages": ["requests==2.34.2"],
            "modules": ["requests"],
            "force": True,
        }
    ]


def test_missing_module_labels_check_requests_stack(monkeypatch):
    monkeypatch.setattr(
        nim_engine.NvidiaNimEngine,
        "_missing_modules",
        classmethod(lambda cls, spec: [spec[1]] if spec[0] == "urllib3" else []),
    )
    monkeypatch.setattr(nim_engine, "_requests_version_matches", lambda: False)
    monkeypatch.setattr(nim_engine, "_requests_runtime_symbols_available", lambda: False)

    missing = nim_engine.NvidiaNimEngine._missing_module_labels()

    assert "urllib3" in missing
    assert "requests==2.34.2" in missing
    assert "NVIDIA NIM requests runtime" in missing


def test_install_common_rejects_cuda_mode():
    try:
        install_common.main(["--cuda", "cuda"])
    except RuntimeError as exc:
        assert str(exc) == "nvidia_nim_cuda_install_not_applicable"
    else:
        raise AssertionError("expected cuda mode rejection")


def test_install_common_verifies_runtime_origins(monkeypatch, tmp_path):
    local_root = tmp_path / "engine"
    local_root.mkdir()
    requests_file = local_root / "requests.py"
    urllib3_file = local_root / "urllib3.py"
    certifi_file = local_root / "certifi.py"
    requests_file.write_text("", encoding="utf-8")
    urllib3_file.write_text("", encoding="utf-8")
    certifi_file.write_text("", encoding="utf-8")

    class FakeContext:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_engine_env = SimpleNamespace(
        engine_env_context=lambda engine_id: FakeContext(),
        bootstrap_engine_env=lambda: local_root,
        isolate_engine_imports=lambda engine_id: None,
    )
    fake_modules = {
        "democrai.core.runtime.dependencies.engine_env": fake_engine_env,
        "requests": SimpleNamespace(
            __file__=str(requests_file),
            post=lambda *args, **kwargs: None,
            Session=lambda: None,
        ),
        "urllib3": SimpleNamespace(__file__=str(urllib3_file)),
        "certifi": SimpleNamespace(__file__=str(certifi_file)),
    }

    monkeypatch.setattr(
        install_common.importlib,
        "import_module",
        lambda name: fake_modules[name],
    )
    monkeypatch.setattr(
        install_common.importlib.metadata,
        "version",
        lambda name: "2.34.2" if name == "requests" else "",
    )

    result = install_common._verify_runtime("auto")

    assert result["requests"] == "2.34.2"
    assert set(result["origins"]) == {"requests", "urllib3", "certifi"}
