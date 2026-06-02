from types import SimpleNamespace

import pytest

import democrai.core.runtime.cli.commands as commands_mod
import democrai.core.runtime.cli.migration as migration_mod
import democrai.sdk.ai as sdk_ai_mod


def test_migration_remaining_branches(monkeypatch):
    # _init_cli_context branches
    ctx = SimpleNamespace(logger=None, config=None)
    monkeypatch.setattr(migration_mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(migration_mod, "LoggerManager", lambda log_dir=None: "logger")
    monkeypatch.setattr(migration_mod, "YamlConfigProvider", lambda _p: "cfg")
    monkeypatch.setattr(migration_mod, "logs_dir", lambda: "/tmp/logs")
    monkeypatch.setattr(migration_mod, "get_data_dir", lambda: "/tmp/data")
    migration_mod._init_cli_context()
    assert ctx.logger == "logger" and ctx.config == "cfg"

    # observability url non-sqlite
    monkeypatch.setattr(migration_mod, "app_ctx", lambda: SimpleNamespace(config=SimpleNamespace(get=lambda k, d=None: "postgresql://x" if k == "storage.observability.url" else "postgres")))
    assert migration_mod._observability_url() == "postgresql://x"

    target = migration_mod.MigrationTarget(
        name="observability",
        label="OBS",
        ini_path="/tmp/a.ini",
        script_location="/tmp/migs",
        metadata_factory=lambda: "meta",
        url_factory=lambda: "clickhouse://x",
    )
    monkeypatch.setattr(migration_mod, "_init_cli_context", lambda: None)
    monkeypatch.setattr(migration_mod, "_resolve_targets", lambda _n: [target])
    monkeypatch.setattr(migration_mod, "_is_clickhouse_observability_target", lambda _t: True)
    called = []
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.storage.observability.providers.clickhouse",
        SimpleNamespace(ClickHouseObsStorage=lambda _url: SimpleNamespace(run_migrations=lambda: called.append("run"))),
    )
    assert migration_mod.migrate("observability") == 0
    assert called == ["run"]
    with pytest.raises(ValueError):
        migration_mod.create_migration("observability", "x")
    with pytest.raises(ValueError):
        migration_mod.rollback("observability", steps=1)
    status = migration_mod._get_status(target)
    assert status.current_revision == "clickhouse-managed"
    monkeypatch.setattr(migration_mod, "_resolve_targets", lambda _n: [target])
    assert migration_mod.migration_status("observability") == 0


def test_commands_remaining_branches(monkeypatch):
    monkeypatch.setattr(commands_mod, "init_module_command_context", lambda _a: None)
    monkeypatch.setattr(commands_mod, "_parse_module_command_tokens", lambda _t: ([], {}))
    monkeypatch.setattr(commands_mod, "module_command_registry", SimpleNamespace(get=lambda _n: None))
    assert commands_mod.run_module_callable("x", [], SimpleNamespace()) == 2

    definition = SimpleNamespace(
        name="mod.cmd",
        lifecycle="callable",
        module_name="mod",
        handler_module="m",
        handler_name="h",
        func=lambda required: required,
    )
    monkeypatch.setattr(commands_mod, "module_command_registry", SimpleNamespace(get=lambda _n: definition, get_all=lambda module_name=None: []))
    monkeypatch.setattr(commands_mod, "app_ctx", lambda: SimpleNamespace(modules=SimpleNamespace(get_module=lambda _n: None, shutdown=lambda: None)))
    assert commands_mod.run_module_callable("mod.cmd", [], SimpleNamespace()) == 2

    # module_status no rows
    monkeypatch.setattr(commands_mod, "app_ctx", lambda: SimpleNamespace(modules=SimpleNamespace(shutdown=lambda: None)))
    monkeypatch.setattr(commands_mod, "module_command_registry", SimpleNamespace(get_all=lambda module_name=None: []))
    monkeypatch.setattr(commands_mod, "module_command_state_store", SimpleNamespace(ensure_registered=lambda _d: None, list_states=lambda module_name=None: []))
    assert commands_mod.module_status(module_name=None, json_output=False, args=SimpleNamespace()) == 0

    # knowledge service unavailable
    monkeypatch.setattr(commands_mod, "init_knowledge_command_context", lambda _a: None)
    monkeypatch.setattr(commands_mod, "app_ctx", lambda: SimpleNamespace(knowledge_service=None))
    assert commands_mod.knowledge_rebuild(source_id="x", args=SimpleNamespace()) == 2


def test_commands_argument_validation_and_table_status(monkeypatch):
    monkeypatch.setattr(commands_mod, "init_module_command_context", lambda _a: None)
    monkeypatch.setattr(commands_mod, "app_ctx", lambda: SimpleNamespace(
        modules=SimpleNamespace(get_module=lambda _n: SimpleNamespace(name="mod"), shutdown=lambda: None)
    ))
    monkeypatch.setattr(commands_mod, "module_command_state_store", SimpleNamespace(
        ensure_registered=lambda _d: None,
        mark_started=lambda _d, owner=None: None,
        finish_run=lambda *a, **k: None,
        list_states=lambda module_name=None: [SimpleNamespace(command_name="mod.cmd", status="running", run_count=2, lease_owner=None, last_error=None, to_dict=lambda: {"next_run_at": "soon"})],
    ))
    monkeypatch.setattr(
        "democrai.core.infrastructure.modules.runtime.get_module_runtime",
        lambda: SimpleNamespace(
            invoke=(lambda **_k: __import__("asyncio").sleep(0, result={"ok": True})),
            stop_module=lambda _n: None,
        ),
    )

    # missing required argument
    definition_missing = SimpleNamespace(
        name="mod.cmd",
        lifecycle="callable",
        module_name="mod",
        handler_module="m",
        handler_name="h",
        func=lambda required: required,
    )
    monkeypatch.setattr(commands_mod, "module_command_registry", SimpleNamespace(get=lambda _n: definition_missing, get_all=lambda module_name=None: [definition_missing]))
    monkeypatch.setattr(commands_mod, "_parse_module_command_tokens", lambda _t: ([], {}))
    with pytest.raises(TypeError):
        commands_mod.run_module_callable("mod.cmd", [], SimpleNamespace())

    # unexpected positional
    definition_pos = SimpleNamespace(
        name="mod.cmd",
        lifecycle="callable",
        module_name="mod",
        handler_module="m",
        handler_name="h",
        func=lambda: None,
    )
    monkeypatch.setattr(commands_mod, "module_command_registry", SimpleNamespace(get=lambda _n: definition_pos, get_all=lambda module_name=None: [definition_pos]))
    monkeypatch.setattr(commands_mod, "_parse_module_command_tokens", lambda _t: (["extra"], {}))
    with pytest.raises(TypeError):
        commands_mod.run_module_callable("mod.cmd", ["extra"], SimpleNamespace())

    # unexpected kwargs
    monkeypatch.setattr(commands_mod, "_parse_module_command_tokens", lambda _t: ([], {"x": 1}))
    with pytest.raises(TypeError):
        commands_mod.run_module_callable("mod.cmd", ["--x", "1"], SimpleNamespace())

    # table status branch
    assert commands_mod.module_status(module_name=None, json_output=False, args=SimpleNamespace()) == 0

    # signature branches: command_name/module_name/varargs/varkw
    definition_sig = SimpleNamespace(
        name="mod.cmd",
        lifecycle="callable",
        module_name="mod",
        handler_module="m",
        handler_name="h",
        func=lambda command_name=None, module_name=None, *args, **kwargs: f"{command_name}:{module_name}:{args}:{kwargs}",
    )
    monkeypatch.setattr(commands_mod, "module_command_registry", SimpleNamespace(get=lambda _n: definition_sig))
    monkeypatch.setattr(commands_mod, "_parse_module_command_tokens", lambda _t: (["p1"], {"k": 1}))
    assert commands_mod.run_module_callable("mod.cmd", ["p1", "k=1"], SimpleNamespace()) == 0

    # error branch in run_module_callable (finish_run failed path)
    monkeypatch.setattr(
        "democrai.core.infrastructure.modules.runtime.get_module_runtime",
        lambda: SimpleNamespace(
            invoke=(lambda **_k: __import__("asyncio").sleep(0, result=(_ for _ in ()).throw(RuntimeError("boom")))),
            stop_module=lambda _n: None,
        ),
    )
    with pytest.raises(RuntimeError):
        commands_mod.run_module_callable("mod.cmd", [], SimpleNamespace())

    # handle_cli_command None branch
    assert commands_mod.handle_cli_command(SimpleNamespace(command=None)) is None


@pytest.mark.asyncio
async def test_sdk_ai_provider_for_objective_branch(monkeypatch):
    monkeypatch.setenv("DEMOCRAI_ENGINE_ORCHESTRATOR", "1")
    async def _get_provider_for_objective(*_a, **_k):
        return {"status": "ok", "provider": "p"}

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_for_objective=_get_provider_for_objective
            )
        ),
    )

    ai = sdk_ai_mod.AI(SimpleNamespace(module_name="m", session={}))
    assert (await ai.get_provider_for_objective("chat"))["provider"] == "p"
