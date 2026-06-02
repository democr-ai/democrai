import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import democrai.core.runtime.dependencies.installer as installer_mod
import democrai.core.runtime.cli.commands as cli_commands_mod
import democrai.core.runtime.cli.migration as migration_mod
import democrai.core.runtime.cli.parsing as cli_parsing_mod
import democrai.core.runtime.cli.reset_install as reset_install_mod


def test_cli_parsing_helpers():
    assert cli_parsing_mod.coerce_cli_value("true") is True
    assert cli_parsing_mod.coerce_cli_value("null") is None
    assert cli_parsing_mod.coerce_cli_value("3") == 3
    assert cli_parsing_mod.coerce_cli_value("3.5") == 3.5
    positional, kwargs = cli_parsing_mod.parse_module_command_tokens(["1", "--flag", "--count", "2", "k=v"])
    assert positional == [1]
    assert kwargs["flag"] is True and kwargs["count"] == 2 and kwargs["k"] == "v"


def test_reset_install_discovery_and_selection(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(reset_install_mod, "get_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(reset_install_mod, "_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(reset_install_mod, "_desktop_jwt_path", lambda: str(tmp_path / "jwt"))
    monkeypatch.setattr(reset_install_mod, "YamlConfigProvider", lambda _p: SimpleNamespace(get=lambda key, default=None: {
        "database.type": "sqlite",
        "database.url": f"sqlite:///{tmp_path / 'democrai.db'}",
        "database.data_type": "sqlite",
        "database.data_url": f"sqlite:///{tmp_path / 'data.db'}",
        "storage.kg.type": "ladybug",
        "storage.vector.type": "sqlite-vec",
        "storage.observability.type": "sqlite",
        "storage.media.type": "local",
        "storage.media.path": str(tmp_path / "assets"),
    }.get(key, default)))
    for name in ("democrai.db", "data.db", "kg.lbug", "vector.db", "observability.db"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "kg.sqlite-wal").write_text("x", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "jwt").write_text("tok", encoding="utf-8")

    _, targets = reset_install_mod.discover_reset_targets()
    assert targets
    media = reset_install_mod.discover_media_reset_target()
    assert media and media.exists
    chosen = reset_install_mod._choose_targets(targets, input_fn=lambda _p: "1,2")
    assert len(chosen) >= 1

    answers = iter(["y", "all", "y", "DELETE MEDIA"])
    out = reset_install_mod.reset_installation(include_media=True, input_fn=lambda _p: next(answers))
    assert out == 0
    assert not (tmp_path / "kg.lbug").exists()
    assert not (tmp_path / "kg.lbug.wal").exists()


def test_cli_command_dispatch_and_module_status(monkeypatch):
    monkeypatch.setattr(cli_commands_mod, "migrate", lambda target: ("migrate", target))
    monkeypatch.setattr(cli_commands_mod, "create_migration", lambda target, message, autogenerate=False, module_name=None: ("create", target, message, autogenerate, module_name))
    monkeypatch.setattr(cli_commands_mod, "rollback", lambda target, steps=None, revision=None: ("rollback", target, steps, revision))
    monkeypatch.setattr(cli_commands_mod, "migration_status", lambda target: ("status", target))
    monkeypatch.setattr(cli_commands_mod, "validate_config_file", lambda _p: {"ok": True})
    monkeypatch.setattr(cli_commands_mod, "print_validation_result", lambda r: 0)
    monkeypatch.setattr(cli_commands_mod, "print_validation_result_json", lambda r: 0)
    monkeypatch.setattr(cli_commands_mod, "reset_installation", lambda include_media=False: 0)
    monkeypatch.setattr(cli_commands_mod, "module_status", lambda **_k: 0)
    monkeypatch.setattr(cli_commands_mod, "knowledge_rebuild", lambda **_k: 0)
    monkeypatch.setattr(cli_commands_mod, "run_module_callable", lambda *_a, **_k: 0)

    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="migrate", target="db")) == ("migrate", "db")
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="create-migration", target="db", message="m", autogenerate=True, module_name=None))[0] == "create"
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="rollback", target="db", steps=1, revision=None))[0] == "rollback"
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="migration-status", target="db"))[0] == "status"
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="validate-config", config_path="/x", json_output=False)) == 0
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="validate-config", config_path="/x", json_output=True)) == 0
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="reset-install", include_media=False)) == 0
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="module-status", module_name=None, json_output=False)) == 0
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="knowledge-rebuild", source_id=None, rebuild_all=True, user_id=None, organization_id=None, source_type=None, limit=None, dry_run=True, json_output=False)) == 0
    assert cli_commands_mod.handle_cli_command(SimpleNamespace(command="module-callable", module_command="x", module_args=[])) == 0
    with pytest.raises(ValueError):
        cli_commands_mod.handle_cli_command(SimpleNamespace(command="other"))


def test_create_module_data_migration_uses_runtime_module_models(monkeypatch, tmp_path: Path):
    module_name = f"migration_probe_{tmp_path.name}".replace("-", "_")
    modules_root = tmp_path / "modules"
    module_dir = modules_root / module_name
    module_dir.mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "models.py").write_text(
        "\n".join(
            [
                "from sqlalchemy import Column, Integer, String",
                "from democrai.sdk.database import get_module_base",
                "",
                "Base = get_module_base()",
                "",
                "class Widget(Base):",
                "    id = Column(Integer, primary_key=True)",
                "    name = Column(String(50), nullable=False)",
            ]
        ),
        encoding="utf-8",
    )

    core_migrations = tmp_path / "core_data_migrations"
    core_migrations.mkdir()
    (core_migrations / "script.py.mako").write_text("script", encoding="utf-8")
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\n", encoding="utf-8")

    captured = {}

    def _revision(cfg, *, message, autogenerate, process_revision_directives=None):
        captured["script_location"] = cfg.get_main_option("script_location")
        captured["version_table"] = cfg.get_main_option("version_table")
        captured["message"] = message
        captured["autogenerate"] = autogenerate
        captured["process_revision_directives"] = process_revision_directives
        captured["tables"] = sorted(cfg.attributes["target_metadata"].tables)
        captured["db_url"] = cfg.attributes["db_url"]
        return object()

    monkeypatch.setattr(migration_mod, "get_runtime_module_dirs", lambda: (str(modules_root),))
    monkeypatch.setattr(migration_mod, "_data_alembic_ini_path", lambda: str(alembic_ini))
    monkeypatch.setattr(migration_mod, "_data_core_migrations_dir", lambda: str(core_migrations))
    monkeypatch.setattr(migration_mod, "_data_url", lambda: "sqlite:///data.db")
    monkeypatch.setattr(migration_mod.command, "revision", _revision)
    monkeypatch.setattr(migration_mod, "_init_cli_context", lambda: None)

    assert (
        migration_mod.create_migration(
            "data",
            "add widget",
            autogenerate=True,
            module_name=module_name,
        )
        == 0
    )

    assert captured["script_location"] == str(module_dir / "migrations")
    assert captured["version_table"] == f"alembic_version_p_{module_name}"
    assert captured["message"] == "add widget"
    assert captured["autogenerate"] is True
    assert captured["process_revision_directives"] is migration_mod._suppress_empty_revision
    assert captured["tables"] == [f"p_{module_name}_widget"]
    assert captured["db_url"] == "sqlite:///data.db"
    assert (module_dir / "migrations" / "env.py").exists()
    assert (module_dir / "migrations" / "script.py.mako").read_text(encoding="utf-8") == "script"


def test_run_module_callable_and_module_status(monkeypatch):
    definition = SimpleNamespace(
        name="mod.cmd",
        lifecycle="callable",
        module_name="mod",
        handler_module="m",
        handler_name="h",
        func=lambda a, flag=False: f"{a}:{flag}",
    )
    monkeypatch.setattr(cli_commands_mod, "init_module_command_context", lambda _a: None)
    monkeypatch.setattr(cli_commands_mod, "_parse_module_command_tokens", lambda tokens: (["x"], {"flag": True}))
    monkeypatch.setattr(cli_commands_mod, "module_command_registry", SimpleNamespace(get=lambda _n: definition, get_all=lambda module_name=None: [definition]))
    monkeypatch.setattr(
        cli_commands_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            modules=SimpleNamespace(get_module=lambda _n: SimpleNamespace(name="mod"), shutdown=lambda: None)
        ),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.modules.runtime.get_module_runtime",
        lambda: SimpleNamespace(
            invoke=(lambda **_k: __import__("asyncio").sleep(0, result={"ok": True})),
            stop_module=lambda _n: None,
        ),
    )
    monkeypatch.setattr(cli_commands_mod, "module_command_state_store", SimpleNamespace(
        ensure_registered=lambda _d: None,
        mark_started=lambda _d, owner=None: None,
        finish_run=lambda *a, **k: None,
        list_states=lambda module_name=None: [SimpleNamespace(command_name="mod.cmd", status="ok", run_count=1, lease_owner=None, last_error=None, to_dict=lambda: {"next_run_at": None})],
    ))
    assert cli_commands_mod.run_module_callable("mod.cmd", ["x", "--flag", "true"], SimpleNamespace()) == 0
    assert cli_commands_mod.module_status(module_name=None, json_output=True, args=SimpleNamespace()) == 0


def test_installer_helpers_and_catalog(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(installer_mod, "get_resource_monitor", lambda: SimpleNamespace(get_resources=lambda: {"has_nvidia_gpu": 1, "vram_total_mb": 1024}))
    assert installer_mod.get_gpu_info()["has_nvidia"] is True
    monkeypatch.setattr(installer_mod, "get_resource_monitor", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert installer_mod.get_gpu_info()["has_nvidia"] is False
    assert installer_mod._norm_arch("AMD64") == "x86_64"

    monkeypatch.setattr(installer_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(installer_mod.platform, "machine", lambda: "x86_64")
    env = installer_mod._runtime_env()
    assert env["os"] == "linux"

    monkeypatch.setattr("democrai.core.runtime.dependencies.engine_env.has_engine_env_context", lambda: False)
    monkeypatch.setattr("democrai.core.runtime.foundation.paths.data_dir", lambda: tmp_path)
    target = installer_mod.get_target_dir()
    assert target.exists()

    monkeypatch.setattr(installer_mod, "runtime_is_frozen", lambda: False)
    monkeypatch.setenv("DEMOCRAI_INSTALL_IN_CURRENT_ENV", "true")
    monkeypatch.setattr("democrai.core.runtime.dependencies.engine_env.has_engine_env_context", lambda: False)
    assert installer_mod._install_into_current_env() is True

    monkeypatch.setattr(installer_mod.importlib.util, "find_spec", lambda m: object() if m == "ok" else None)
    assert installer_mod._import_any(["missing", "ok"]) is True
    monkeypatch.setattr(installer_mod.importlib, "import_module", lambda m: object() if m == "ok" else (_ for _ in ()).throw(ImportError("x")))
    assert installer_mod._verify_imports(["missing", "ok"])[0] is True


def test_import_any_search_path_requires_complete_dotted_module(tmp_path: Path):
    google_root = tmp_path / "google"
    google_root.mkdir()

    assert installer_mod._import_any(["google"], search_path=tmp_path) is True
    assert installer_mod._import_any(["google.genai"], search_path=tmp_path) is False

    genai_root = google_root / "genai"
    genai_root.mkdir()
    (genai_root / "__init__.py").write_text("", encoding="utf-8")
    importlib.invalidate_caches()
    assert installer_mod._import_any(["google.genai"], search_path=tmp_path) is True


def test_installer_resolve_validate_and_install(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(installer_mod, "_runtime_env", lambda: {"os": "linux", "arch": "x86_64", "gpu": {"has_nvidia": False}, "python": "3.12"})
    monkeypatch.setattr(installer_mod, "_verify_imports", lambda _m: (True, None))
    monkeypatch.setattr(installer_mod, "_import_any", lambda _m, **_k: True)
    monkeypatch.setattr(installer_mod, "run_pip_subprocess", lambda _a, **_k: None)
    monkeypatch.setattr(installer_mod, "run_pip_internal", lambda _a, **_k: None)
    monkeypatch.setattr(installer_mod, "_load_state", lambda _t: {"deps": {}})
    saved = {}
    monkeypatch.setattr(installer_mod, "_save_state", lambda _t, state: saved.update(state))
    monkeypatch.setattr(installer_mod, "get_target_dir", lambda: tmp_path)
    monkeypatch.setattr(installer_mod, "_install_into_current_env", lambda: True)
    assert installer_mod.install_dependency("librosa", force=False) is True

    monkeypatch.setattr(installer_mod, "_install_into_current_env", lambda: False)
    assert installer_mod.install_dependency("librosa", force=False) is True
    assert "deps" in saved

    with pytest.raises(RuntimeError):
        installer_mod.ensure_dependency_installed("mod")


def test_install_python_packages(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(installer_mod, "_verify_imports", lambda _m: (True, None))
    monkeypatch.setattr(installer_mod, "_import_any", lambda _m, **_k: True)
    monkeypatch.setattr(installer_mod, "run_pip_subprocess", lambda _a, **_k: None)
    monkeypatch.setattr(installer_mod, "run_pip_internal", lambda _a, **_k: None)
    monkeypatch.setattr(installer_mod, "_load_state", lambda _t: {"deps": {}})
    saved = {}
    monkeypatch.setattr(installer_mod, "_save_state", lambda _t, state: saved.update(state))
    monkeypatch.setattr(installer_mod, "get_target_dir", lambda: tmp_path)
    monkeypatch.setattr(installer_mod, "_runtime_env", lambda: {"os": "linux", "arch": "x86_64", "gpu": {"has_nvidia": False}, "python": "3.12"})

    monkeypatch.setattr(installer_mod, "_install_into_current_env", lambda: True)
    assert installer_mod.install_python_packages(["a", "b"], modules=["ma"]) is True

    monkeypatch.setattr(installer_mod, "_install_into_current_env", lambda: False)
    assert installer_mod.install_python_packages(["a", "b"], modules=["ma"]) is True
    assert "deps" in saved


def test_reset_install_additional_branches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(reset_install_mod, "get_data_dir", lambda: str(tmp_path))
    assert reset_install_mod._config_path().endswith("config.yaml")
    assert reset_install_mod._desktop_jwt_path().endswith("/.democrai/auth_token")
    assert reset_install_mod._sqlite_path_from_url(None) is None
    assert reset_install_mod._sqlite_path_from_url("postgres://x") is None
    assert reset_install_mod._sqlite_path_from_url("sqlite:///tmp/a.db") == "/tmp/a.db"
    assert reset_install_mod._sqlite_path_from_url("sqlite://localhost/tmp/a.db") is None

    # no config path branch discovers only existing defaults
    (tmp_path / "democrai.db").write_text("x", encoding="utf-8")
    (tmp_path / "kg.sqlite-wal").write_text("x", encoding="utf-8")
    cfg_path, targets = reset_install_mod.discover_reset_targets(str(tmp_path / "missing.yaml"))
    assert cfg_path.endswith("missing.yaml")
    assert {target.key for target in targets} == {"db", "kg"}
    kg_target = next(target for target in targets if target.key == "kg")
    assert kg_target.sidecar_paths == (
        str(tmp_path / "kg.sqlite-wal"),
        str(tmp_path / "kg.sqlite-shm"),
    )

    # config with non sqlite branches
    cfg_real = tmp_path / "cfg.yaml"
    cfg_real.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        reset_install_mod,
        "YamlConfigProvider",
        lambda _p: SimpleNamespace(
            get=lambda key, default=None: {
                "database.type": "postgres",
                "database.data_type": "postgres",
                "storage.kg.type": "neo4j",
                "storage.vector.type": "faiss",
                "storage.observability.type": "clickhouse",
                "storage.media.type": "s3",
            }.get(key, default)
        ),
    )
    _, targets2 = reset_install_mod.discover_reset_targets(str(cfg_real))
    assert targets2 == []
    assert reset_install_mod.discover_media_reset_target(str(cfg_real)) is None

    # media target with missing config but default assets existing
    (tmp_path / "assets").mkdir(exist_ok=True)
    media = reset_install_mod.discover_media_reset_target(str(tmp_path / "missing2.yaml"))
    assert media and media.exists
    assert reset_install_mod.discover_media_reset_target(str(tmp_path / "missing3.yaml")) is not None
    (tmp_path / "assets").rmdir()
    assert reset_install_mod.discover_media_reset_target(str(tmp_path / "missing3.yaml")) is None

    # chooser branches
    none_targets = reset_install_mod._choose_targets(
        [reset_install_mod.ResetTarget("x", "X", "/p", exists=False)],
        input_fn=lambda _p: "all",
    )
    assert none_targets == []
    many = [
        reset_install_mod.ResetTarget("a", "A", "/a", True),
        reset_install_mod.ResetTarget("b", "B", "/b", True),
    ]
    assert reset_install_mod._choose_targets(many, input_fn=lambda _p: "") == []
    assert len(reset_install_mod._choose_targets(many, input_fn=lambda _p: "all")) == 2
    assert len(reset_install_mod._choose_targets(many, input_fn=lambda _p: "1,1,9")) == 1

    # clear jwt none branch
    monkeypatch.setattr(reset_install_mod, "_desktop_jwt_path", lambda: str(tmp_path / "missing.jwt"))
    assert reset_install_mod._clear_desktop_jwt() is None

    # reset cancelled
    monkeypatch.setattr(reset_install_mod, "discover_reset_targets", lambda: (str(cfg_real), many))
    monkeypatch.setattr(reset_install_mod, "discover_media_reset_target", lambda _p: None)
    assert reset_install_mod.reset_installation(include_media=False, input_fn=lambda _p: "n") == 1

    # reset with no config/jwt and media phrase invalid
    media_dir = tmp_path / "assets2"
    media_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(
        reset_install_mod,
        "discover_media_reset_target",
        lambda _p: reset_install_mod.ResetTarget("media", "Media", str(media_dir), True),
    )
    monkeypatch.setattr(reset_install_mod, "_desktop_jwt_path", lambda: str(tmp_path / "missing.jwt"))
    missing_cfg = tmp_path / "does_not_exist.yaml"
    monkeypatch.setattr(reset_install_mod, "discover_reset_targets", lambda: (str(missing_cfg), many))
    answers = iter(["y", "none", "y", "WRONG"])
    assert reset_install_mod.reset_installation(include_media=True, input_fn=lambda _p: next(answers)) == 0

    # include_media true but no media target
    monkeypatch.setattr(reset_install_mod, "discover_media_reset_target", lambda _p: None)
    answers2 = iter(["y", "none"])
    assert reset_install_mod.reset_installation(include_media=True, input_fn=lambda _p: next(answers2)) == 0

    # include_media false success branch and non-existing selected target branch
    cfg_ok = tmp_path / "cfg_ok.yaml"
    cfg_ok.write_text("x", encoding="utf-8")
    missing_target = reset_install_mod.ResetTarget("m", "M", str(tmp_path / "not_exist.db"), False)
    monkeypatch.setattr(reset_install_mod, "discover_reset_targets", lambda: (str(cfg_ok), [missing_target]))
    answers3 = iter(["y", "all"])
    assert reset_install_mod.reset_installation(include_media=False, input_fn=lambda _p: next(answers3)) == 0


def test_installer_additional_branches(monkeypatch, tmp_path: Path):
    assert installer_mod._norm_arch("mips") == "mips"
    assert installer_mod._norm_arch("aarch64") == "arm64"
    monkeypatch.setattr("democrai.core.runtime.dependencies.engine_env.has_engine_env_context", lambda: True)
    assert installer_mod._install_into_current_env() is False
    monkeypatch.setattr("democrai.core.runtime.dependencies.engine_env.has_engine_env_context", lambda: False)
    monkeypatch.setattr(installer_mod, "runtime_is_frozen", lambda: True)
    assert installer_mod._install_into_current_env() is False
    monkeypatch.setattr(installer_mod, "runtime_is_frozen", lambda: False)
    monkeypatch.setenv("DEMOCRAI_INSTALL_IN_CURRENT_ENV", "no")
    assert installer_mod._install_into_current_env() is False

    # get_target_dir with engine env context
    monkeypatch.setattr("democrai.core.runtime.dependencies.engine_env.has_engine_env_context", lambda: True)
    monkeypatch.setattr("democrai.core.runtime.dependencies.engine_env.get_engine_local_env_path", lambda: tmp_path / "engine_env")
    assert installer_mod.get_target_dir().name == "engine_env"

    monkeypatch.setattr("democrai.core.runtime.dependencies.extractor_env.has_extractor_env_context", lambda: True)
    monkeypatch.setattr("democrai.core.runtime.dependencies.extractor_env.get_extractor_local_env_path", lambda: tmp_path / "extractor_env")
    assert installer_mod.get_target_dir().name == "extractor_env"
    monkeypatch.setattr("democrai.core.runtime.dependencies.extractor_env.has_extractor_env_context", lambda: False)

    class _Stdout:
        def __iter__(self):
            return iter(())

        def close(self):
            return None

    monkeypatch.setattr(
        installer_mod,
        "subprocess",
        SimpleNamespace(
            PIPE=object(),
            STDOUT=object(),
            Popen=lambda *args, **kwargs: SimpleNamespace(
                stdout=_Stdout(),
                wait=lambda: 0,
                returncode=0,
            ),
        ),
        raising=False,
    )
    installer_mod.run_pip_subprocess(["x"])
    monkeypatch.setattr(
        installer_mod,
        "subprocess",
        SimpleNamespace(
            PIPE=object(),
            STDOUT=object(),
            Popen=lambda *args, **kwargs: SimpleNamespace(
                stdout=_Stdout(),
                wait=lambda: 2,
                returncode=2,
            ),
        ),
        raising=False,
    )
    with pytest.raises(RuntimeError):
        installer_mod.run_pip_subprocess(["x"])

    import sys as _sys

    captured_cmds = []

    def _subprocess_with_popen(returncode):
        return SimpleNamespace(
            PIPE=object(),
            STDOUT=object(),
            Popen=lambda cmd, **kwargs: (
                captured_cmds.append(cmd),
                SimpleNamespace(
                    stdout=_Stdout(),
                    wait=lambda: returncode,
                    returncode=returncode,
                ),
            )[1],
        )

    monkeypatch.setattr(
        installer_mod,
        "subprocess",
        _subprocess_with_popen(0),
        raising=False,
    )
    monkeypatch.setattr(installer_mod, "runtime_is_frozen", lambda: False)
    installer_mod.run_pip_internal(["x"])
    assert captured_cmds[-1][:5] == [installer_mod.sys.executable, "-m", "pip", "install", "--no-input"]
    monkeypatch.setattr(
        installer_mod,
        "subprocess",
        _subprocess_with_popen(1),
        raising=False,
    )
    monkeypatch.setattr(installer_mod, "runtime_is_frozen", lambda: False)
    with pytest.raises(RuntimeError):
        installer_mod.run_pip_internal(["x"])

    captured_cmds.clear()
    monkeypatch.setattr(
        installer_mod,
        "subprocess",
        _subprocess_with_popen(0),
        raising=False,
    )
    monkeypatch.setattr(installer_mod, "runtime_is_frozen", lambda: True)
    installer_mod.run_pip_internal(["x"])
    assert captured_cmds[-1][:3] == [installer_mod.sys.executable, "--pip-helper", "install"]
    monkeypatch.setattr(installer_mod.importlib.util, "find_spec", lambda _m: None)
    assert installer_mod._import_any(["a", "b"]) is False
    monkeypatch.setattr(
        installer_mod.importlib,
        "import_module",
        lambda _m: (_ for _ in ()).throw(ImportError("x")),
    )
    ok, err = installer_mod._verify_imports(["a", "b"])
    assert ok is False and err is not None

    monkeypatch.setattr(installer_mod, "_install_into_current_env", lambda: True)
    pip_calls = []
    monkeypatch.setattr(
        installer_mod,
        "run_pip_subprocess",
        lambda args, **kwargs: pip_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(installer_mod, "_verify_imports", lambda _m: (False, RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        installer_mod.install_python_packages(
            ["pkg"],
            modules=["m"],
            force=False,
            index_url="https://idx",
            extra_index_url="https://eidx",
            allow_source=True,
            extra_pip_args=["--no-binary", "pkg"],
            env={"CMAKE_ARGS": "-DTEST=on"},
        )
    assert "--index-url" in pip_calls[0][0] and "--extra-index-url" in pip_calls[0][0]
    assert "--no-binary" in pip_calls[0][0]
    assert pip_calls[0][1]["env"] == {"CMAKE_ARGS": "-DTEST=on"}

    # install target env cache-hit and failure branches
    monkeypatch.setattr(installer_mod, "_install_into_current_env", lambda: False)
    monkeypatch.setattr(installer_mod, "get_target_dir", lambda: tmp_path)
    monkeypatch.setattr(
        installer_mod,
        "_load_state",
        lambda _t: {
            "deps": {
                "python_packages:pkg|index=|extra_index=|allow_source=0|pip_args=|env=": {
                    "installed": True
                }
            }
        },
    )
    monkeypatch.setattr(installer_mod, "_import_any", lambda _m, **_k: True)
    assert installer_mod.install_dependency("pkg", force=False) is True

    monkeypatch.setattr(installer_mod, "_load_state", lambda _t: {"deps": {}})
    monkeypatch.setattr(installer_mod, "_import_any", lambda _m, **_k: False)
    monkeypatch.setattr(installer_mod, "run_pip_internal", lambda _a, **_k: None)
    monkeypatch.setattr(installer_mod, "_verify_imports", lambda _m: (False, RuntimeError("x")))
    monkeypatch.setattr(
        "democrai.core.runtime.dependencies.engine_env.has_engine_env_context",
        lambda: False,
    )
    with pytest.raises(RuntimeError):
        installer_mod.install_python_packages(["pkg"], modules=["m"], force=True)

    monkeypatch.setattr(
        "democrai.core.runtime.dependencies.engine_env.has_engine_env_context",
        lambda: True,
    )
    assert installer_mod.install_python_packages(["pkg"], modules=["m"], force=True) is True

    # successful target install path with sys.path insertion after install
    monkeypatch.setattr(installer_mod, "_load_state", lambda _t: {"deps": {}})
    monkeypatch.setattr(installer_mod, "_verify_imports", lambda _m: (True, None))
    monkeypatch.setattr(
        "democrai.core.runtime.dependencies.engine_env.has_engine_env_context",
        lambda: False,
    )
    saved = {}
    monkeypatch.setattr(installer_mod, "_save_state", lambda _t, s: saved.update(s))
    target2 = tmp_path / "dep_env_2"
    target2.mkdir(exist_ok=True)
    monkeypatch.setattr(installer_mod, "get_target_dir", lambda: target2)
    import sys

    if str(target2) in sys.path:
        sys.path.remove(str(target2))
    assert installer_mod.install_dependency("pkg", force=True) is True
    assert "deps" in saved

    with pytest.raises(RuntimeError):
        installer_mod.ensure_dependency_installed("unknown")


def test_install_dependencies_batches_target_env(monkeypatch, tmp_path):
    monkeypatch.setattr(installer_mod, "_install_into_current_env", lambda: False)
    monkeypatch.setattr(installer_mod, "get_target_dir", lambda: tmp_path)
    monkeypatch.setattr(installer_mod, "_load_state", lambda _t: {"deps": {}})
    monkeypatch.setattr(installer_mod, "_import_any", lambda _m, **_k: False)
    monkeypatch.setattr(
        "democrai.core.runtime.dependencies.engine_env.has_engine_env_context",
        lambda: True,
    )
    pip_calls = []
    monkeypatch.setattr(
        installer_mod,
        "run_pip_internal",
        lambda args, **kwargs: pip_calls.append((args, kwargs)),
    )

    assert installer_mod.install_python_packages(
        ["a", "b", "c"],
        modules=["k_mod", "k2_mod"],
        force=False,
        extra_index_url="https://x",
        extra_pip_args=["--no-binary", "a"],
        env={"CMAKE_ARGS": "-DTEST=on"},
    ) is True
    assert len(pip_calls) == 1
    assert pip_calls[0][0].count("b") == 1
    assert "--no-binary" in pip_calls[0][0]
    assert pip_calls[0][1]["extra_env"] == {"CMAKE_ARGS": "-DTEST=on"}


def test_llamacpp_install_uses_cuda_source_build_on_nvidia(monkeypatch):
    llama_mod = importlib.import_module("engines.llamacpp.engine")
    calls = []
    monkeypatch.setattr(llama_mod, "has_nvidia", lambda: True)
    monkeypatch.setattr(
        llama_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)) or True,
    )

    llama_mod.LlamaCppEngine._install(force=True)

    assert calls == [
        (
            ["llama-cpp-python"],
            {
                "modules": ["llama_cpp"],
                "force": True,
                "extra_pip_args": ["--no-binary", "llama-cpp-python"],
                "env": {
                    "CMAKE_ARGS": "-DGGML_CUDA=on",
                    "FORCE_CMAKE": "1",
                },
            },
        )
    ]


def test_llamacpp_install_uses_standard_package_without_nvidia(monkeypatch):
    llama_mod = importlib.import_module("engines.llamacpp.engine")
    calls = []
    monkeypatch.setattr(llama_mod, "has_nvidia", lambda: False)
    monkeypatch.setattr(
        llama_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)) or True,
    )

    llama_mod.LlamaCppEngine._install(force=False)

    assert calls == [
        (
            ["llama-cpp-python"],
            {
                "modules": ["llama_cpp"],
                "force": False,
            },
        )
    ]
