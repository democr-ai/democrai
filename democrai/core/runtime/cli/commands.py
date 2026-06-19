from __future__ import annotations

import asyncio
import inspect
import json
import os

from democrai.core.infrastructure.modules.command_state_store import module_command_state_store
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.bootstrap.config_validation import (
    print_validation_result,
    print_validation_result_json,
    validate_config_file,
)
from .migration import create_migration, migrate, migration_status, rollback
from democrai.core.runtime.foundation.paths import logs_dir
from democrai.core.runtime.foundation.registry import module_command_registry
from .reset_install import reset_installation
from .parsing import parse_module_command_tokens as _parse_module_command_tokens
from .install_engines import install_engines
from .install_extractors import install_extractors
from .setup import setup_application


def init_module_command_context(args) -> None:
    from democrai.core.infrastructure.observability.logger.manager import LoggerManager
    from democrai.core.runtime.bootstrap.bootstrap_pipeline import RuntimeBootstrapper

    ctx = app_ctx()
    if ctx.logger is None:
        ctx.logger = LoggerManager(log_dir=str(logs_dir()))

    bootstrapper = RuntimeBootstrapper()
    bootstrapper.init_config(ctx)
    bootstrapper.init_storage(ctx)
    bootstrapper.init_modules(ctx, args)
    if not ctx.setup_mode:
        bootstrapper.run_migrations(ctx)


def init_knowledge_command_context(args) -> None:
    from democrai.core.infrastructure.observability.logger.manager import LoggerManager
    from democrai.core.runtime.bootstrap.bootstrap_pipeline import RuntimeBootstrapper

    ctx = app_ctx()
    if ctx.logger is None:
        ctx.logger = LoggerManager(log_dir=str(logs_dir()))

    bootstrapper = RuntimeBootstrapper()
    bootstrapper.init_config(ctx)
    bootstrapper.init_storage(ctx)
    if not ctx.setup_mode:
        bootstrapper.run_migrations(ctx)


def knowledge_rebuild(
    *,
    source_id=None,
    rebuild_all=False,
    user_id=None,
    organization_id=None,
    source_type=None,
    limit=None,
    dry_run=False,
    json_output=False,
    args=None,
) -> int:
    init_knowledge_command_context(args)
    ctx = app_ctx()
    service = getattr(ctx, "knowledge_service", None)
    repository = getattr(service, "repository", None) if service is not None else None
    if service is None or repository is None:
        print("Knowledge service unavailable.")
        return 2

    if source_id is not None:
        selected_sources = repository.list_sources(
            include_deleted=False,
            source_id=source_id,
            limit=1,
        )
    elif rebuild_all:
        selected_sources = repository.list_sources(
            include_deleted=False,
            user_id=user_id,
            organization_id=organization_id,
            source_type=source_type,
            limit=limit,
        )
    else:
        raise ValueError("knowledge_rebuild requires source_id or rebuild_all=True")

    rows = [
        {
            "source_id": source.id,
            "user_id": source.user_id,
            "organization_id": source.organization_id or None,
            "source_type": source.source_type,
            "status": source.status,
        }
        for source in selected_sources
    ]
    if dry_run:
        payload = {"mode": "dry-run", "count": len(rows), "sources": rows}
        if json_output:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Selected {len(rows)} knowledge source(s) for rebuild.")
            for row in rows:
                print(
                    f"- {row['source_id']} user={row['user_id']} org={row['organization_id'] or '-'} type={row['source_type']}"
                )
        return 0

    results = service.admin_rebuild_sources(
        source_id=source_id,
        user_id=user_id if source_id is None else None,
        organization_id=organization_id if source_id is None else None,
        source_type=source_type if source_id is None else None,
        limit=limit if source_id is None else None,
    )
    payload = {
        "count": len(results),
        "sources": [
            {
                "source_id": result.source_id,
                "user_id": result.user_id,
                "organization_id": result.organization_id,
                "source_type": result.source_type,
                "outbox_ids": list(result.outbox_ids),
            }
            for result in results
        ],
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Queued rebuild for {len(results)} knowledge source(s).")
        for row in payload["sources"]:
            print(
                f"- {row['source_id']} user={row['user_id']} org={row['organization_id'] or '-'} type={row['source_type']} jobs={len(row['outbox_ids'])}"
            )
    return 0


def run_module_callable(command_name: str, cli_args: list[str], args) -> int:
    from democrai.core.infrastructure.modules.runtime import get_module_runtime

    init_module_command_context(args)

    definition = module_command_registry.get(command_name)
    if definition is None or definition.lifecycle != "callable":
        print(f"Unknown module callable command: {command_name}")
        return 2

    module = app_ctx().modules.get_module(definition.module_name)
    if module is None:
        print(f"Module not loaded for command: {command_name}")
        return 2

    positional, cli_kwargs = _parse_module_command_tokens(cli_args)
    signature = inspect.signature(definition.func)
    call_args, call_kwargs, consumed_kwargs = [], {}, set()
    positional_index = 0
    cli_owner = f"cli:{os.getpid()}"
    module_command_state_store.ensure_registered(definition)
    module_command_state_store.mark_started(definition, owner=cli_owner)

    for parameter in signature.parameters.values():
        if parameter.name in {"sdk", "module_sdk", "democrai_sdk"}:
            continue
        if parameter.name == "command_name":
            call_kwargs[parameter.name] = definition.name
            continue
        if parameter.name == "module_name":
            call_kwargs[parameter.name] = module.name
            continue
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            call_args.extend(positional[positional_index:])
            positional_index = len(positional)
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            for key, value in cli_kwargs.items():
                if key not in consumed_kwargs:
                    call_kwargs[key] = value
            consumed_kwargs.update(cli_kwargs.keys())
            continue
        if parameter.name in cli_kwargs:
            call_kwargs[parameter.name] = cli_kwargs[parameter.name]
            consumed_kwargs.add(parameter.name)
            continue
        if (
            parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
            and positional_index < len(positional)
        ):
            call_args.append(positional[positional_index])
            positional_index += 1
            continue
        if parameter.default is inspect.Parameter.empty:
            raise TypeError(f"missing required argument: {parameter.name}")

    extra_positional = positional[positional_index:]
    extra_kwargs = {
        key: value for key, value in cli_kwargs.items() if key not in consumed_kwargs
    }
    if extra_positional:
        raise TypeError(f"unexpected positional arguments: {extra_positional}")
    if extra_kwargs:
        raise TypeError(f"unexpected keyword arguments: {sorted(extra_kwargs)}")

    try:
        result = asyncio.run(
            get_module_runtime().invoke(
                module=module,
                operation="command",
                payload={
                    "handler_module": definition.handler_module,
                    "handler_name": definition.handler_name,
                    "command_name": definition.name,
                    "call_args": list(call_args),
                    "call_kwargs": dict(call_kwargs),
                    "include_stop_event": ("stop_event" in signature.parameters),
                },
                session={},
                metadata={"mode": "module_command", "command_name": definition.name},
                persistent=False,
            )
        )
        module_command_state_store.finish_run(
            definition.name,
            owner=cli_owner,
            status="completed",
        )
    except Exception as exc:
        module_command_state_store.finish_run(
            definition.name,
            owner=cli_owner,
            status="failed",
            last_error=str(exc),
        )
        raise
    finally:
        get_module_runtime().stop_module(module.name)
        app_ctx().modules.shutdown()

    if result is not None:
        print(result)
    return 0


def module_status(*, module_name: str | None = None, json_output: bool = False, args=None) -> int:
    init_module_command_context(args)
    try:
        definitions = module_command_registry.get_all(module_name=module_name)
        for definition in definitions:
            module_command_state_store.ensure_registered(definition)

        states = {
            state.command_name: state
            for state in module_command_state_store.list_states(module_name=module_name)
        }
        rows = []
        for definition in definitions:
            state = states.get(definition.name)
            rows.append(
                {
                    "module": definition.module_name,
                    "command": definition.name,
                    "lifecycle": definition.lifecycle,
                    "status": state.status if state else "idle",
                    "runs": state.run_count if state else 0,
                    "next_run_at": state.to_dict()["next_run_at"] if state else None,
                    "lease_owner": state.lease_owner if state else None,
                    "last_error": state.last_error if state else None,
                }
            )

        if json_output:
            print(json.dumps(rows, indent=2, sort_keys=True))
            return 0
        if not rows:
            print("No module commands registered.")
            return 0

        header = (
            f"{'PLUGIN':<16} {'COMMAND':<28} {'TYPE':<12} {'STATUS':<12} {'RUNS':<6} {'NEXT RUN':<24}"
        )
        print(header)
        print("-" * len(header))
        for row in rows:
            print(
                f"{row['module']:<16} {row['command']:<28} {row['lifecycle']:<12} {row['status']:<12} {row['runs']:<6} {(row['next_run_at'] or '-'): <24}"
            )
        return 0
    finally:
        app_ctx().modules.shutdown()


def handle_cli_command(args) -> int | None:
    if args.command is None:
        return None
    if args.command == "migrate":
        return migrate(args.target)
    if args.command == "create-migration":
        return create_migration(
            args.target,
            args.message,
            autogenerate=args.autogenerate,
            module_name=args.module_name,
        )
    if args.command == "rollback":
        return rollback(args.target, steps=args.steps, revision=args.revision)
    if args.command == "migration-status":
        return migration_status(args.target)
    if args.command == "validate-config":
        result = validate_config_file(args.config_path)
        if args.json_output:
            return print_validation_result_json(result)
        return print_validation_result(result)
    if args.command == "setup":
        return setup_application(
            config_path=args.config_path,
            yes=args.yes,
            json_output=args.json_output,
            args=args,
        )
    if args.command == "install-engines":
        return install_engines(
            config_path=args.config_path,
            reset_mode=args.reset_mode,
            yes=args.yes,
            json_output=args.json_output,
            args=args,
        )
    if args.command == "install-extractors":
        return install_extractors(
            config_path=args.config_path,
            reset_mode=args.reset_mode,
            yes=args.yes,
            json_output=args.json_output,
            args=args,
        )
    if args.command == "reset-install":
        return reset_installation(include_media=args.include_media)
    if args.command == "module-status":
        return module_status(
            module_name=args.module_name,
            json_output=args.json_output,
            args=args,
        )
    if args.command == "knowledge-rebuild":
        return knowledge_rebuild(
            source_id=args.source_id,
            rebuild_all=args.rebuild_all,
            user_id=args.user_id,
            organization_id=args.organization_id,
            source_type=args.source_type,
            limit=args.limit,
            dry_run=args.dry_run,
            json_output=args.json_output,
            args=args,
        )
    if args.command == "module-callable":
        return run_module_callable(args.module_command, args.module_args, args)
    raise ValueError(f"Unknown command: {args.command}")
