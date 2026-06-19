import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import democrai.sdk.media as media_mod
import democrai.sdk.system as system_mod
import democrai.sdk.tasks as tasks_mod
import democrai.core.application.setup.finalization as setup_finalization_mod
from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy.models import AccessResource, AccessSubject
from democrai.core.runtime.foundation.app import RequestContext
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import reset_req_ctx
from democrai.core.runtime.foundation.app import set_req_ctx


def _access_rule(subject_kind: str, subject: str, resource_type: str, operation: str, target: str):
    return AccessManifestRule(
        subject=AccessSubject.create(subject_kind, subject),
        resource=AccessResource.create(
            resource_type=resource_type,
            operation=operation,
            target=target,
        ),
    )


def test_tasks_context_and_registry_helpers(monkeypatch):
    sdk = SimpleNamespace(
        session={"user": {"id": 7, "organization_id": 10, "role": "admin", "access_level": 1}, "session_key": "s1"},
        module_name="mod",
        module_path="/tmp/mod",
    )
    tasks = tasks_mod.Tasks(sdk)

    class _Current:
        request_id = "r1"
        user = 9
        role = "user"
        organization_id = 11
        access_level = 2
        channel = "ipc"
        app = "app"
        session_key = "sess"
        client_ip = "127.0.0.1"
        action_name = "x"
        stream_id = "st"

    monkeypatch.setattr(tasks_mod, "req_ctx", lambda: _Current())
    ctx = tasks._capture_request_context()
    assert ctx and ctx.request_id == "r1"
    built = tasks._build_request_context(task_id="t1")
    assert built.request_id == "r1"

    monkeypatch.setattr(tasks_mod, "req_ctx", lambda: (_ for _ in ()).throw(LookupError()))
    built2 = tasks._build_request_context(task_id="t2")
    assert built2.request_id == "sdk-task:t2"

    module_access = [
        _access_rule("module", "mod", "filesystem", "read", "/extra"),
        _access_rule("module", "mod", "network", "receive", "api.local"),
    ]
    monkeypatch.setattr(
        tasks_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            modules=SimpleNamespace(
                get_module=lambda _n: SimpleNamespace(access=module_access)
            )
        ),
    )

    guard_calls = []
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.process_guard.process_guard_context",
        lambda **kwargs: (guard_calls.append(kwargs), __import__("contextlib").nullcontext())[1],
    )
    guard = tasks._runtime_guard(built2)
    with guard:
        pass
    assert guard_calls and guard_calls[-1].get("allow_subprocess") is False
    assert guard_calls[-1]["access"] == module_access

    async def _coro():
        return 1

    assert asyncio.run(tasks._coerce_coroutine(_coro())) == 1
    monkeypatch.setattr(tasks_mod, "task_registry", {"x": lambda **_k: 5})
    assert asyncio.run(tasks._coerce_coroutine("x")) == 5
    with pytest.raises(ValueError):
        tasks._coerce_coroutine("missing")


@pytest.mark.asyncio
async def test_tasks_run_background_blocking_and_updates(monkeypatch):
    sdk = SimpleNamespace(
        session={"user": {"id": 7, "organization_id": 10}, "session_key": "s1"},
        module_name="mod",
        module_path="/tmp/mod",
    )
    tasks = tasks_mod.Tasks(sdk)

    async def _submit(*_a, **_k):
        return "task-1"

    async def _update(*_a, **_k):
        return None

    async def _request(_tid, comps):
        return {"ok": True, "components": comps}

    manager = SimpleNamespace(
        submit=_submit,
        update_progress=_update,
        request_confirmation=_request,
    )
    monkeypatch.setattr("democrai.core.runtime.foundation.app.app_ctx", lambda: SimpleNamespace(task_manager=manager, modules=None))
    out = await tasks.run_background(lambda: None, label="L")
    assert out == "task-1"

    with pytest.raises(TypeError):
        await tasks.run_blocking("not-callable")
    context_flags = []
    monkeypatch.setattr(
        tasks,
        "_task_runtime_context",
        lambda _ctx, allow_subprocess=False: (
            context_flags.append(bool(allow_subprocess)),
            __import__("contextlib").nullcontext(),
        )[1],
    )
    monkeypatch.setattr(
        tasks,
        "_registered_module",
        lambda: SimpleNamespace(
            access=[
                _access_rule("module", "mod", "filesystem", "read", "/tmp/mod"),
                _access_rule("module", "mod", "network", "receive", "https://api.local"),
            ]
        ),
    )
    assert await tasks.run_blocking(lambda x: x + 1, 2) == 3
    assert context_flags and context_flags[-1] is False

    run_calls = []
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.launcher.run_subprocess",
        lambda cmd, **kwargs: run_calls.append((cmd, kwargs))
        or SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    out_run = await tasks.run_subprocess(["ffmpeg", "-version"], text=True)
    assert out_run.returncode == 0
    assert run_calls and run_calls[-1][0][0] == "ffmpeg"
    assert context_flags[-1] is True
    passed_env = run_calls[-1][1]["env"]
    assert passed_env["DEMOCRAI_NETWORK_SUBJECT"] == "mod"
    assert passed_env["DEMOCRAI_USER_ID"] == "7"
    assert passed_env["DEMOCRAI_ORGANIZATION_ID"] == "10"
    assert passed_env["DEMOCRAI_SESSION_KEY"] == "s1"
    access = json.loads(passed_env["DEMOCRAI_ACCESS"])
    assert access[0]["resource"]["target"] == "/tmp/mod"
    assert access[1]["resource"]["target"] == "https://api.local"

    with pytest.raises(TypeError):
        await tasks.run_subprocess("ffmpeg")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await tasks.run_subprocess(["", "-version"])

    await tasks.update_progress("t1", 0.5)
    builder = tasks_mod.Builder()
    assert (await tasks.request_confirmation("t1", builder))["ok"] is True

    monkeypatch.setattr("democrai.core.runtime.foundation.app.app_ctx", lambda: SimpleNamespace(task_manager=None, modules=None))
    with pytest.raises(RuntimeError):
        await tasks.request_confirmation("t1", builder)


def test_media_facade_operations(tmp_path: Path, monkeypatch):
    storage = {}
    upload_calls = []
    move_updates = []
    delete_calls = []
    fake_media = SimpleNamespace(
        load=lambda p: storage[p],
        save=lambda p, b: (storage.__setitem__(p, bytes(b)), p)[1],
        delete=lambda p: storage.pop(p, None),
    )
    monkeypatch.setattr(media_mod, "app_ctx", lambda: SimpleNamespace(media=fake_media))
    monkeypatch.setattr(media_mod, "update_media_upload_storage_path", lambda **_kwargs: None)
    monkeypatch.setattr(
        media_mod,
        "store_uploaded_media",
        lambda **kwargs: upload_calls.append(kwargs) or SimpleNamespace(storage_path=f"media/mod/{kwargs['original_filename']}"),
    )
    monkeypatch.setattr(
        media_mod,
        "update_media_upload_storage_path",
        lambda **kwargs: move_updates.append(kwargs),
    )
    monkeypatch.setattr(
        media_mod,
        "delete_media_upload_by_storage_path",
        lambda **kwargs: delete_calls.append(kwargs),
    )
    monkeypatch.setattr(
        media_mod,
        "resolve_client_media_source",
        lambda **kwargs: f"/media/modules/{kwargs['module_name']}/assets/{kwargs['value']}",
    )

    sdk = SimpleNamespace(module_name="mod", session={}, module_path=str(tmp_path))
    media = media_mod.Media(sdk)
    storage["a.bin"] = b"abc"
    assert media.view("a.bin") == b"abc"
    token = set_req_ctx(
        RequestContext(
            request_id="req-media-add",
            user=7,
            role="user",
            organization_id=10,
            access_level=3,
            channel="test",
            app=app_ctx(),
        )
    )
    try:
        assert media.add("nested/out.bin", b"x") == "media/mod/out.bin"
    finally:
        reset_req_ctx(token)
    assert upload_calls and upload_calls[-1]["original_filename"] == "out.bin"
    assert upload_calls[-1]["user_id"] == 7
    assert upload_calls[-1]["organization_id"] == 10
    assert upload_calls[-1]["access_level"] == 3
    assert media.move("a.bin", "b.bin") == "b.bin"
    assert storage["b.bin"] == b"abc"
    assert move_updates[-1]["old_storage_path"] == "a.bin"
    media.delete("b.bin")
    assert "b.bin" not in storage
    assert delete_calls[-1]["storage_path"] == "b.bin"
    assert media.get_public_url("a.bin") == "/media/proxy?module_name=mod&url=%2Fmedia%2Fmodules%2Fmod%2Fassets%2Fa.bin"
    assert media.get_public_url("") is None

    with pytest.raises(ValueError):
        media.add("", b"x")
    with pytest.raises(ValueError):
        media.add("x", b"")
    with pytest.raises(ValueError):
        media.view("")


def test_media_add_model_variants(tmp_path: Path, monkeypatch):
    storage = {}
    fake_media = SimpleNamespace(
        load=lambda p: storage[p],
        save=lambda p, b: (storage.__setitem__(p, bytes(b)), p)[1],
        save_file=lambda p, source_path: (
            storage.__setitem__(p, Path(source_path).read_bytes()),
            p,
        )[1],
        delete=lambda p: storage.pop(p, None),
    )
    monkeypatch.setattr(media_mod, "app_ctx", lambda: SimpleNamespace(media=fake_media))
    monkeypatch.setattr(media_mod, "update_media_upload_storage_path", lambda **_kwargs: None)
    monkeypatch.setattr(media_mod, "get_data_dir", lambda: str(tmp_path))
    sdk = SimpleNamespace(module_name="mod", session={}, module_path=str(tmp_path))
    media = media_mod.Media(sdk)

    out = media.add_model("m", payload=b"abc", filename="f.bin")
    assert out == "models/m/f.bin"

    storage["media/src.bin"] = b"raw"
    out2 = media.add_model("m2", source_path="media/src.bin")
    assert out2 == "models/m2/src.bin"

    d = tmp_path / "dir"
    d.mkdir()
    (d / "a.txt").write_text("a", encoding="utf-8")
    out3 = media.add_model("m3", source_path=str(d))
    assert out3 == "models/m3"
    assert json.loads(storage["models/m3/.democrai-model-manifest.json"].decode("utf-8"))["files"] == ["a.txt"]

    f = tmp_path / "f.bin"
    f.write_bytes(b"b")
    out4 = media.add_model("m4", source_path=str(f))
    assert out4 == "models/m4/f.bin"

    def _download_url_to_file(cls, url, *, target_path, token=None, **kwargs):
        del cls, url, token, kwargs
        Path(target_path).write_bytes(b"url-model")

    monkeypatch.setattr(
        media_mod.Media,
        "_download_url_to_file",
        classmethod(_download_url_to_file),
    )
    out5 = media.add_model_from_source(
        "m5",
        source={"type": "url", "url": "https://example.test/model.bin"},
    )
    assert out5 == "models/m5/model.bin"
    assert storage["models/m5/model.bin"] == b"url-model"

    monkeypatch.setattr(
        media_mod.Media,
        "_download_huggingface_file_to_path",
        classmethod(
            lambda cls, repo_id, revision, remote_path, token, target_path, **kwargs: Path(
                target_path
            ).write_bytes(f"{repo_id}:{remote_path}".encode("utf-8"))
        ),
    )
    out6 = media.add_model_from_source(
        "m6",
        source={
            "type": "huggingface",
            "repo": "owner/repo",
            "files": ["nested/model.gguf"],
        },
    )
    assert out6 == "models/m6/model.gguf"
    assert storage["models/m6/model.gguf"] == b"owner/repo:nested/model.gguf"

    out6_target = media.add_model_from_source(
        "m6target",
        source={
            "type": "huggingface",
            "repo": "owner/repo",
            "files": ["nested/model.gguf"],
            "target": "models/nested/model.gguf",
        },
    )
    assert out6_target == "models/m6target"
    assert storage["models/m6target/nested/model.gguf"] == b"owner/repo:nested/model.gguf"
    assert json.loads(
        storage["models/m6target/.democrai-model-manifest.json"].decode("utf-8")
    )["files"] == ["nested/model.gguf"]

    monkeypatch.setattr(
        media_mod.Media,
        "_list_huggingface_snapshot_files",
        classmethod(lambda cls, repo_id, revision, token: ["tokenizer.json"]),
    )
    out7 = media.add_model_from_source(
        "m7",
        source={"type": "huggingface", "repo": "owner/snapshot", "snapshot": True},
    )
    assert out7 == "models/m7"
    assert storage["models/m7/tokenizer.json"] == b"owner/snapshot:tokenizer.json"

    out8 = media.add_model_from_source(
        "m8",
        source={
            "type": "huggingface",
            "repo": "owner/targeted",
            "snapshot": True,
            "target": "nested-model",
        },
    )
    assert out8 == "models/m8"
    assert storage["models/m8/nested-model/tokenizer.json"] == b"owner/targeted:tokenizer.json"


def test_remote_model_storage_uses_framework_media_bypass(monkeypatch, tmp_path: Path):
    from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
    from democrai.core.infrastructure.storage.media.providers.local import LocalMediaProvider

    sdk = SimpleNamespace(module_name="system", session={}, module_path=str(tmp_path))
    media = media_mod.Media(sdk)
    provider = LocalMediaProvider(str(tmp_path / "media"))
    monkeypatch.setattr(media_mod, "app_ctx", lambda: SimpleNamespace(media=provider))
    monkeypatch.setattr(
        media_mod.Media,
        "_download_huggingface_file_to_path",
        classmethod(
            lambda cls, repo_id, revision, remote_path, token, target_path, **kwargs: Path(
                target_path
            ).write_bytes(b"model")
        ),
    )

    with process_guard_context(
        subject="system",
        subject_kind="module",
        access=(),
        include_runtime_access=False,
        inherit_parent_access=False,
    ):
        out = media.add_model_from_source(
            "guarded",
            source={
                "type": "huggingface",
                "repo": "owner/repo",
                "files": ["nested/model.bin"],
            },
        )

    assert out == "models/guarded/model.bin"
    assert (tmp_path / "media" / "models" / "guarded" / "model.bin").read_bytes() == b"model"


def test_media_provider_and_add_model_error_branches(tmp_path: Path, monkeypatch):
    sdk = SimpleNamespace(module_name="mod", session={}, module_path=str(tmp_path))

    monkeypatch.setattr(media_mod, "app_ctx", lambda: SimpleNamespace(media=None))
    with pytest.raises(RuntimeError):
        media_mod.require_media_provider()

    storage = {}
    def _save_file(path: str, source_path: str):
        storage[path] = Path(source_path).read_bytes()
        return path

    fake_media = SimpleNamespace(
        load=lambda p: storage[p],
        save=lambda p, b: storage.setdefault(p, bytes(b)) or p,
        save_file=_save_file,
        delete=lambda p: storage.pop(p, None),
    )
    monkeypatch.setattr(media_mod, "app_ctx", lambda: SimpleNamespace(media=fake_media))
    media = media_mod.Media(sdk)

    with pytest.raises(ValueError):
        media.add_model("m")
    with pytest.raises(ValueError):
        media.add_model("m", payload=b"x", source_path="x.bin")
    with pytest.raises(ValueError):
        media.add_model("m", payload=b"x", filename="")

    with pytest.raises(ValueError):
        media.add_model("m", source_path=str(tmp_path / "missing.bin"))

    source_dir = tmp_path / "src"
    (source_dir / "nested").mkdir(parents=True)
    (source_dir / "nested" / "f.txt").write_text("ok", encoding="utf-8")
    assert media.add_model("m-dir", source_path=str(source_dir)) == "models/m-dir"
    assert storage["models/m-dir/nested/f.txt"] == b"ok"

    class _FakePathObj:
        def __init__(self, raw: str):
            self.raw = raw
            self.name = ""

        def expanduser(self):
            return self

        def is_dir(self):
            return False

        def is_file(self):
            return True

        def read_bytes(self):
            return b"x"

    monkeypatch.setattr(media_mod, "Path", _FakePathObj)
    with pytest.raises(ValueError):
        media.add_model("m-file", source_path="fake", filename="")

    class _FakePathMediaNameEmpty:
        def __init__(self, raw: str):
            self.raw = raw
            self.name = ""

        def expanduser(self):
            return self

        def is_dir(self):
            return False

        def is_file(self):
            return False

    monkeypatch.setattr(media_mod, "Path", _FakePathMediaNameEmpty)
    with pytest.raises(ValueError):
        media.add_model("m-media", source_path="media/x", filename="")


def test_system_modules_sessions_metrics_and_setup(monkeypatch, tmp_path):
    cfg = {
        "session.idle_ttl_seconds": 60,
        "database.type": "sqlite",
        "database.url": "sqlite:///db",
        "storage.media.type": "local",
        "storage.media.path": "/tmp/media",
        "storage.kg.type": "ladybug",
        "storage.vector.type": "sqlite-vec",
        "storage.observability.type": "sqlite",
    }
    class _Cfg:
        def get(self, key, default=None):
            return cfg.get(key, default)

    modules = [
        SimpleNamespace(name="b", label="Beta", version="1", icon="i", description="d"),
        SimpleNamespace(name="a", label="Alpha", version="1", icon="i", description="d"),
    ]
    context = SimpleNamespace(
        modules=SimpleNamespace(get_all_modules=lambda: modules),
        config=_Cfg(),
        setup_mode=True,
        is_setup_mode=True,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )
    monkeypatch.setattr(system_mod, "app_ctx", lambda: context)
    monkeypatch.setattr(system_mod, "is_module_locked_for_user", lambda *_args, **_kwargs: False)

    sdk = SimpleNamespace(
        session={"user": {"id": 1}},
        models=SimpleNamespace(module_locks=SimpleNamespace(list=lambda **_k: {"rows": [{"module_name": "a"}]})),
        module_name="mod",
    )
    system = system_mod.System(sdk)
    listed = system.modules.list()
    assert listed[0]["module_name"] == "a"
    active = system.modules.list_active_for_user()
    assert [m["module_name"] for m in active] == ["a", "b"]

    class _Query:
        def __init__(self):
            self.filtered = False
        def filter(self, _expr):
            self.filtered = True
            return self
        def count(self):
            return 3
    class _Sess:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def query(self, _model):
            return _Query()
    monkeypatch.setattr(system_mod, "SessionLocal", _Sess)
    assert system.sessions.count_active() == 3

    monkeypatch.setattr("psutil.virtual_memory", lambda: SimpleNamespace(total=1024 * 1024 * 100, available=1024 * 1024 * 40, percent=60.0))
    monkeypatch.setattr("psutil.cpu_percent", lambda interval=0.0: 12.3)
    monkeypatch.setattr(system_mod, "get_resource_monitor", lambda: SimpleNamespace(get_resources=lambda: {"ram_total_mb": 100, "ram_free_mb": 40, "vram_total_mb": 10, "vram_free_mb": 4, "has_nvidia_gpu": 1}))
    metrics = system.metrics.read()
    assert metrics["cpu_percent"] == 12.3
    assert metrics["ram_used_mb"] == 60
    assert metrics["vram_used_mb"] == 6

    assert system.setup.is_enabled() is True
    data_dir = tmp_path / "data"
    monkeypatch.setattr(system_mod, "get_data_dir", lambda: str(data_dir))
    assert system.temp_dir() == str(data_dir / "tmp")
    assert (data_dir / "tmp").is_dir()

    finalize_calls = []
    def _finalize(**kwargs):
        finalize_calls.append(kwargs)
        context.setup_mode = False
    monkeypatch.setattr(system_mod, "finalize_setup_runtime", _finalize)
    system.setup.finalize("admin", "pw")
    assert finalize_calls == [
        {"admin_user": "admin", "admin_pass": "pw", "admin_email": None}
    ]
    assert context.setup_mode is False

    system.log("hello")


def test_system_additional_branches(monkeypatch):
    context = SimpleNamespace(
        modules=None,
        config=SimpleNamespace(get=lambda key, default=None: {"session.idle_ttl_seconds": "bad"}.get(key, default)),
        setup_mode=False,
        is_setup_mode=False,
        logger=None,
    )
    monkeypatch.setattr(system_mod, "app_ctx", lambda: context)

    sdk = SimpleNamespace(
        session={},
        models=SimpleNamespace(module_locks=SimpleNamespace(list=lambda **_k: {"rows": [None, {"module_name": "m1", "role_id": 1}]})),
        module_name="mod",
    )
    system = system_mod.System(sdk)
    monkeypatch.setattr(system_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        system_mod,
        "get_resource_monitor",
        lambda: SimpleNamespace(get_resources=lambda: {"has_nvidia_gpu": 1}),
    )
    assert system.os_name() == "linux"
    assert system.has_nvidia() is True
    assert system.modules.list() == []
    assert system.modules.list_active_for_user(user_id=None) == []

    class _Query:
        def filter(self, _expr):
            return self

        def count(self):
            return 1

    class _Sess:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def query(self, _model):
            return _Query()

    monkeypatch.setattr(system_mod, "SessionLocal", _Sess)
    assert system.sessions.count_active() == 1
    assert system.setup.is_enabled() is False

    monkeypatch.setattr(system_mod, "app_ctx", lambda: (_ for _ in ()).throw(RuntimeError("ctx")))
    assert system.setup.is_enabled() is False

    def _finalize(**kwargs):
        if not context.setup_mode:
            raise PermissionError("APPLICATION NOT IN SETUP MODE")
    monkeypatch.setattr(system_mod, "finalize_setup_runtime", _finalize)
    with pytest.raises(PermissionError):
        system.setup.finalize("admin", "pw")

    # logger missing branch should be a no-op
    monkeypatch.setattr(system_mod, "app_ctx", lambda: context)
    assert system.log("x") is None

    # non-sqlite db finalize branch
    context.setup_mode = True
    context.is_setup_mode = True
    context.config = SimpleNamespace(
        get=lambda key, default=None: {
            "database.type": "postgres",
            "database.url": "postgresql://demo",
            "storage.media.type": "local",
            "storage.media.path": "/tmp/media",
            "storage.kg.type": "ladybug",
            "storage.vector.type": "sqlite-vec",
            "storage.observability.type": "sqlite",
            "storage.observability.exporters.otlp.enabled": False,
        }.get(key, default)
    )
    context.network = SimpleNamespace(core=None)
    monkeypatch.setattr(system_mod, "app_ctx", lambda: context)
    db_calls = []
    def _finalize_postgres(**kwargs):
        db_calls.append(kwargs)
    monkeypatch.setattr(system_mod, "finalize_setup_runtime", _finalize_postgres)
    system.setup.finalize("admin", "pw")
    assert db_calls == [
        {"admin_user": "admin", "admin_pass": "pw", "admin_email": None}
    ]


def test_system_setup_finalize_process_restrictions_branches(monkeypatch):
    context = SimpleNamespace(
        setup_mode=True,
        is_setup_mode=True,
        config=SimpleNamespace(
            get=lambda key, default=None: {
                "database.type": "sqlite",
                "database.url": "sqlite:///db",
                "storage.media.type": "local",
                "storage.media.path": "/tmp/media",
                "storage.kg.type": "ladybug",
                "storage.vector.type": "sqlite-vec",
                "storage.observability.type": "sqlite",
                "storage.observability.exporters.otlp.enabled": False,
            }.get(key, default)
        ),
        logger=SimpleNamespace(info=lambda *a, **k: None),
        network=SimpleNamespace(core=None),
    )
    calls: list[str] = []
    monkeypatch.setattr(system_mod, "app_ctx", lambda: context)
    def _finalize_with_restrictions(**kwargs):
        calls.append("apply")
        context.setup_mode = False
    monkeypatch.setattr(system_mod, "finalize_setup_runtime", _finalize_with_restrictions)

    system = system_mod.System(SimpleNamespace(module_name="mod", session={}, models=SimpleNamespace(module_locks=SimpleNamespace(list=lambda **_k: {"rows": []}))))
    system.setup.finalize("admin", "pw")
    assert calls == ["apply"]
    assert context.setup_mode is False

    context.setup_mode = True
    context.is_setup_mode = True
    warn_calls: list[str] = []
    def _finalize_warn(**kwargs):
        __import__("warnings").warn("[Sandbox] process restrictions failed: nope")
    monkeypatch.setattr("warnings.warn", lambda msg: warn_calls.append(str(msg)))
    monkeypatch.setattr(system_mod, "finalize_setup_runtime", _finalize_warn)
    system.setup.finalize("admin", "pw")
    assert warn_calls and "process restrictions failed" in warn_calls[-1]


def test_setup_finalization_syncs_loaded_module_rbac(monkeypatch):
    module = SimpleNamespace(name="system", path="/mods/system")
    context = SimpleNamespace(
        modules=SimpleNamespace(get_all_modules=lambda: [module]),
        logger=SimpleNamespace(warning=lambda *a, **k: None, error=lambda *a, **k: None),
    )
    sync_calls = []
    monkeypatch.setattr(
        "democrai.core.application.auth.service.sync_module_authorization",
        lambda module_name, manifest: sync_calls.append((module_name, manifest)),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.modules.loading._load_module_rbac_manifest",
        lambda loaded_module: {"permissions": ["engine.model.manage"]},
    )

    setup_finalization_mod._sync_loaded_module_authorization(context)

    assert sync_calls == [("system", {"permissions": ["engine.model.manage"]})]


def test_setup_finalization_rbac_sync_failure_logs_warning(monkeypatch):
    module = SimpleNamespace(name="system", path="/mods/system")
    warnings: list[str] = []
    errors: list[str] = []
    context = SimpleNamespace(
        modules=SimpleNamespace(get_all_modules=lambda: [module]),
        logger=SimpleNamespace(
            warning=lambda message, *a, **k: warnings.append(str(message)),
            error=lambda message, *a, **k: errors.append(str(message)),
        ),
    )
    monkeypatch.setattr(
        "democrai.core.application.auth.service.sync_module_authorization",
        lambda module_name, manifest: (_ for _ in ()).throw(RuntimeError("db_down")),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.modules.loading._load_module_rbac_manifest",
        lambda loaded_module: {"permissions": ["engine.model.manage"]},
    )

    setup_finalization_mod._sync_loaded_module_authorization(context)

    assert warnings == ["[Setup] Failed to sync module RBAC for system: db_down"]
    assert errors == []
