from pathlib import Path
from types import SimpleNamespace

from democrai.core.runtime.dependencies import installer_env as installer_env_mod
from democrai.core.runtime.dependencies import installer_state as installer_state_mod
from democrai.core.runtime.lifecycle import cleanup as cleanup_mod


def test_installer_state_load_and_save(tmp_path: Path):
    state = installer_state_mod.load_state(tmp_path)
    assert state == {"deps": {}}

    installer_state_mod.save_state(tmp_path, {"deps": {"ffmpeg": "ok"}})
    reloaded = installer_state_mod.load_state(tmp_path)
    assert reloaded == {"deps": {"ffmpeg": "ok"}}

    installer_state_mod.state_file(tmp_path).write_text("{bad json", encoding="utf-8")
    assert installer_state_mod.load_state(tmp_path) == {"deps": {}}


def test_installer_env_runtime_and_engine_support(monkeypatch):
    monkeypatch.setattr(
        installer_env_mod,
        "get_resource_monitor",
        lambda: SimpleNamespace(get_resources=lambda: {"has_nvidia_gpu": 1, "vram_total_mb": 4096}),
    )
    env = installer_env_mod.runtime_env()
    assert env["gpu"]["has_nvidia"] is True
    assert env["gpu"]["vram_mb"] == 4096
    assert installer_env_mod.norm_arch("AMD64") == "x86_64"
    assert installer_env_mod.norm_arch("aarch64") == "arm64"

    monkeypatch.setattr(
        "democrai.core.application.ai.engine.runtime.check_engine_supported_runtime",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("engine_runtime_class_not_found:unknown")),
    )
    missing = installer_env_mod.engine_support_status("unknown", env)
    assert missing["supported"] is False

    monkeypatch.setattr(
        "democrai.core.application.ai.engine.runtime.check_engine_supported_runtime",
        lambda **_kwargs: {"supported": True, "reason": ""},
    )
    ok = installer_env_mod.engine_support_status("demo", env)
    assert ok["supported"] is True
    assert installer_env_mod.is_engine_supported("demo", env) is True


def test_cleanup_shutdown_flow(monkeypatch):
    info_logs = []
    error_logs = []
    monkeypatch.setattr(
        cleanup_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: info_logs.append(a),
                error=lambda *a, **k: error_logs.append(a),
            )
        ),
    )

    terminated = []
    monkeypatch.setattr(
        cleanup_mod,
        "process_supervisor",
        SimpleNamespace(
            terminate=lambda proc: terminated.append(proc),
            terminate_all=lambda: terminated.append("all"),
        ),
    )

    ai_shutdowns = []
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.engine.provider_manager",
        SimpleNamespace(genai_manager=SimpleNamespace(shutdown=lambda: ai_shutdowns.append("genai"))),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(shutdown=lambda: ai_shutdowns.append("modules"))),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.engine.runtime",
        SimpleNamespace(get_engine_runtime=lambda: SimpleNamespace(shutdown=lambda: ai_shutdowns.append("engine"))),
    )

    ctx = SimpleNamespace(
        os_sandbox_helper_process="helper",
        network=SimpleNamespace(
            core=SimpleNamespace(session_service=SimpleNamespace(shutdown=lambda: None)),
            stop=lambda: terminated.append("network_stop"),
        ),
        obs_maintenance_service=SimpleNamespace(shutdown=lambda: None),
        engine_runtime=SimpleNamespace(shutdown=lambda: ai_shutdowns.append("engine")),
    )
    cleanup_mod.run_shutdown_cleanup(ctx, reloader=SimpleNamespace(stop=lambda: terminated.append("reloader")), child_proc="child")

    assert "reloader" in terminated
    assert "child" in terminated
    assert "helper" in terminated
    assert "network_stop" in terminated
    assert "all" in terminated
    assert ai_shutdowns == ["genai", "modules", "engine"]
    assert info_logs


def test_installer_env_extra_branches(monkeypatch):
    # get_gpu_info exception path
    monkeypatch.setattr(
        installer_env_mod,
        "get_resource_monitor",
        lambda: (_ for _ in ()).throw(RuntimeError("x")),
    )
    gpu_info = installer_env_mod.get_gpu_info()
    assert gpu_info["has_nvidia"] is False
    assert gpu_info["vram_mb"] == 0

    # empty engine id
    status_empty = installer_env_mod.engine_support_status("", env={})
    assert status_empty["supported"] is False

    # non-dict env -> runtime_env branch
    monkeypatch.setattr(installer_env_mod, "runtime_env", lambda: {"os": "linux"})

    monkeypatch.setattr(
        "democrai.core.application.ai.engine.runtime.check_engine_supported_runtime",
        lambda **_kwargs: {"supported": False, "reason": "not-supported"},
    )
    out = installer_env_mod.engine_support_status("Demo", env="invalid")
    assert out["engine_id"] == "demo"
    assert out["supported"] is False
    assert out["reason"] == "not-supported"
    assert installer_env_mod.norm_arch("mips64") == "mips64"



def test_cleanup_error_paths(monkeypatch):
    info_logs = []
    error_logs = []
    monkeypatch.setattr(
        cleanup_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: info_logs.append(a),
                error=lambda *a, **k: error_logs.append(a),
            )
        ),
    )

    terminated = []
    monkeypatch.setattr(
        cleanup_mod,
        "process_supervisor",
        SimpleNamespace(
            terminate=lambda proc: terminated.append(proc),
            terminate_all=lambda: terminated.append("all"),
        ),
    )

    # force AI cleanup import failure path
    monkeypatch.delitem(__import__("sys").modules, "democrai.core.application.ai.engine.provider_manager", raising=False)

    ctx = SimpleNamespace(
        os_sandbox_helper_process=None,
        network=SimpleNamespace(
            core=SimpleNamespace(
                session_service=SimpleNamespace(
                    shutdown=lambda: (_ for _ in ()).throw(RuntimeError("session fail"))
                )
            ),
            stop=lambda: terminated.append("network_stop"),
        ),
        obs_maintenance_service=SimpleNamespace(
            shutdown=lambda: (_ for _ in ()).throw(RuntimeError("obs fail"))
        ),
    )

    cleanup_mod.run_shutdown_cleanup(ctx, reloader=None, child_proc=None)
    assert "network_stop" in terminated
    assert "all" in terminated
    assert error_logs  # session/obs/ai failures logged
    assert info_logs


def test_cleanup_ai_exception_logged(monkeypatch):
    info_logs = []
    error_logs = []
    monkeypatch.setattr(
        cleanup_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: info_logs.append(a),
                error=lambda *a, **k: error_logs.append(a),
            )
        ),
    )
    monkeypatch.setattr(
        cleanup_mod,
        "process_supervisor",
        SimpleNamespace(terminate=lambda *_a, **_k: None, terminate_all=lambda: None),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.engine.provider_manager",
        SimpleNamespace(genai_manager=SimpleNamespace(shutdown=lambda: (_ for _ in ()).throw(RuntimeError("ai fail")))),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(shutdown=lambda: None)),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.engine.runtime",
        SimpleNamespace(get_engine_runtime=lambda: SimpleNamespace(shutdown=lambda: None)),
    )
    ctx = SimpleNamespace(
        os_sandbox_helper_process=None,
        network=SimpleNamespace(
            core=SimpleNamespace(session_service=SimpleNamespace(shutdown=lambda: None)),
            stop=lambda: None,
        ),
        obs_maintenance_service=None,
    )
    cleanup_mod.run_shutdown_cleanup(ctx, reloader=None, child_proc=None)
    assert info_logs
    assert error_logs
