from __future__ import annotations

from typing import Any

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.utils.actions.engine.config import (
    default_engine_name,
    provider_display_name,
    render_engine_config_modal,
)
from modules.system.utils.actions.engine.lifecycle import (
    runtime_config_ready_for_activation,
    start_engine_install_task,
)
from modules.system.utils.actions.engine.store import (
    page_state_update,
    provider_store_values,
)
from modules.system.utils.actions.user.index import build_aux_surface_messages


async def _provider_requirements(module_sdk, provider: str) -> dict[str, Any]:
    return await module_sdk.engines.provider_requirements(provider_id=provider)


async def _activate_engine_or_prompt_install(
    module_sdk,
    *,
    engine_id: int,
    provider: str,
    session: dict[str, Any],
    close_surface_id: str = "modal",
):
    requirements = await module_sdk.engines.activation_requirements(
        engine_registry_id=engine_id,
    )
    missing = [
        dict(item)
        for item in list(requirements.get("missing_dependencies") or [])
        if isinstance(item, dict)
    ]
    if not missing:
        activation = await module_sdk.engines.activate_instance(
            engine_registry_id=engine_id,
        )
        if not bool(activation.get("ready")):
            message = str(activation.get("activation_message") or "").strip()
            if not message:
                message = module_sdk.i18n.t(
                    "system.engine.activation.not_ready.default"
                )
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {
                        "level": "error",
                        "message": message,
                    },
                ),
                module_sdk.effects.render(),
            )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                [
                    {"deleteSurface": {"surfaceId": close_surface_id}},
                    page_state_update(
                        provider_store_values(
                            module_sdk,
                            provider=provider,
                            status=str(activation.get("status") or "active"),
                            activation_ready=True,
                            activation_message="",
                        )
                    ),
                ]
            ),
            module_sdk.effects.render(),
        )

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {"deleteSurface": {"surfaceId": close_surface_id}},
                page_state_update(
                    provider_store_values(
                        module_sdk,
                        provider=provider,
                        status="installing",
                    )
                ),
            ]
        ),
        *(
            await start_engine_install_task(
                module_sdk,
                engine_id=engine_id,
                provider=provider,
                session=session,
                on_finish={
                    "name": "nav",
                    "context": {
                        "type": "nav",
                        "path": f"/system/engine/provider/{provider}",
                    },
                },
            )
        ),
    )


def _install_already_running_response(module_sdk):
    return module_sdk.effects.respond(
        module_sdk.effects.notify(
            "toast",
            {
                "level": "info",
                "message": module_sdk.i18n.t(
                    "system.engine.install.invalid_status",
                    context={"status": "installing"},
                ),
            },
        ),
        module_sdk.effects.render(),
    )


@action("install_engine_from_instance_overview")
@permission_required(["system.engine.manage"])
async def install_engine_from_instance_overview(
    ctx: dict[str, Any], session: dict, module_sdk
):
    if "engine_id" not in ctx:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t("system.engine.invalid_engine_id"),
                },
            ),
            module_sdk.effects.render(),
        )

    engine_id = int(ctx["engine_id"])
    try:
        engine = module_sdk.models.engine_registry.view(engine_id)
    except Exception:
        engine = None

    if not isinstance(engine, dict):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t("system.engine.invalid_engine_id"),
                },
            ),
            module_sdk.effects.render(),
        )

    provider = str(engine.get("provider") or "").strip().lower()
    requirements = await _provider_requirements(module_sdk, provider)
    if not provider or not bool(requirements.get("supported")):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "warning",
                    "message": module_sdk.i18n.t(
                        "system.engine.install.provider_not_supported"
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    missing_dependencies = [
        dict(item)
        for item in list(requirements.get("missing_dependencies") or [])
        if isinstance(item, dict)
    ]
    if bool(requirements.get("configurable")) and not missing_dependencies:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "warning",
                    "message": module_sdk.i18n.t(
                        "system.engine.install.configurable_not_supported"
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    current_status = str(engine.get("status") or "").strip().lower()
    if current_status == "installing":
        return _install_already_running_response(module_sdk)

    can_retry_error = current_status == "error"
    if current_status != "uninstalled" and not can_retry_error:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "info",
                    "message": module_sdk.i18n.t(
                        "system.engine.install.invalid_status",
                        context={"status": current_status or "unknown"},
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    return module_sdk.effects.respond(
        *(
            await start_engine_install_task(
                module_sdk,
                engine_id=engine_id,
                provider=provider,
                force=can_retry_error,
                session=session,
                mount_id="engine_instance_overview_task_mount_col",
                card_id_prefix="engine_instance_install_task",
                on_finish={
                    "name": "nav",
                    "context": {
                        "type": "nav",
                        "path": f"/system/engine/instance/{engine_id}/view",
                    },
                },
            )
        )
    )


@action("install_engine")
@permission_required(["system.engine.manage"])
async def install_engine(ctx: dict[str, Any], session: dict, module_sdk):
    if "engine_id" not in ctx:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t("system.engine.invalid_engine_id"),
                },
            ),
            module_sdk.effects.render(),
        )

    engine_id = int(ctx["engine_id"])
    try:
        engine = module_sdk.models.engine_registry.view(engine_id)
    except Exception:
        engine = None

    if not isinstance(engine, dict):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t("system.engine.invalid_engine_id"),
                },
            ),
            module_sdk.effects.render(),
        )

    provider = str(engine.get("provider") or "").strip().lower()
    requirements = await _provider_requirements(module_sdk, provider)
    if not provider or not bool(requirements.get("supported")):
        return module_sdk.effects.respond(module_sdk.effects.render())

    missing_dependencies = [
        dict(item)
        for item in list(requirements.get("missing_dependencies") or [])
        if isinstance(item, dict)
    ]
    if bool(requirements.get("configurable")) and not missing_dependencies:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.engine.install.configurable_not_supported"
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    current_status = str(engine.get("status") or "").strip().lower()
    if current_status == "installing":
        return _install_already_running_response(module_sdk)

    can_retry_error = current_status == "error"
    if current_status != "uninstalled" and not can_retry_error:
        return module_sdk.effects.respond(module_sdk.effects.render())

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                page_state_update(
                    provider_store_values(
                        module_sdk,
                        provider=provider,
                        status="installing",
                    )
                )
            ]
        ),
        *(
            await start_engine_install_task(
                module_sdk,
                engine_id=engine_id,
                provider=provider,
                force=can_retry_error,
                session=session,
                on_finish={
                    "name": "nav",
                    "context": {
                        "type": "nav",
                        "path": f"/system/engine/provider/{provider}",
                    },
                },
            )
        ),
    )


@action("activate_engine")
@permission_required(["system.engine.manage"])
async def activate_engine(ctx: dict[str, Any], session: dict, module_sdk):
    engine_id = (
        int(ctx["engine_id"])
        if "engine_id" in ctx and ctx["engine_id"] is not None
        else None
    )
    provider = str(ctx["provider"]).strip().lower() if "provider" in ctx else ""
    engine: dict[str, Any] | None = None
    if engine_id is not None:
        try:
            current = module_sdk.models.engine_registry.view(engine_id)
        except Exception:
            current = None
        if isinstance(current, dict):
            engine = current
            if not provider:
                provider = str(engine.get("provider") or "").strip().lower()
    if not provider:
        return module_sdk.effects.respond(module_sdk.effects.render())
    requirements = await _provider_requirements(module_sdk, provider)
    if not bool(requirements.get("configurable")) and not bool(
        requirements.get("supported")
    ):
        return module_sdk.effects.respond(module_sdk.effects.render())

    if engine_id is None and bool(requirements.get("configurable")):
        provider_name = provider_display_name(module_sdk, provider)
        modal_builder = render_engine_config_modal(
            module_sdk,
            provider=provider,
            provider_name=provider_name,
            engine_id=None,
            initial_values={"name": default_engine_name(provider, module_sdk)},
            activate_after_save=True,
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                build_aux_surface_messages(
                    module_sdk, modal_builder, surface_id="drawer"
                )
            )
        )

    if engine_id is None or not isinstance(engine, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())

    if str(engine.get("status") or "").strip().lower() == "active":
        return module_sdk.effects.respond(module_sdk.effects.render())

    activation_requirements = await module_sdk.engines.activation_requirements(
        engine_registry_id=engine_id,
    )
    if str(activation_requirements.get("reason") or "").strip() == "missing_config":
        provider_name = provider_display_name(module_sdk, provider)
        config = engine.get("config") if isinstance(engine.get("config"), dict) else {}
        modal_builder = render_engine_config_modal(
            module_sdk,
            provider=provider,
            provider_name=provider_name,
            engine_id=engine_id,
            initial_values={
                **config,
                "name": str(engine.get("name") or provider),
            },
            activate_after_save=True,
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                build_aux_surface_messages(
                    module_sdk, modal_builder, surface_id="drawer"
                )
            )
        )

    runtime_config_status = await runtime_config_ready_for_activation(
        module_sdk,
        provider=provider,
        engine=engine,
    )
    if not bool(runtime_config_status.get("ready")):
        message = str(runtime_config_status.get("message") or "").strip()
        if not message:
            message = module_sdk.i18n.t("system.engine.activation.not_ready.default")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": message,
                },
            ),
            module_sdk.effects.render(),
        )

    return await _activate_engine_or_prompt_install(
        module_sdk,
        engine_id=engine_id,
        provider=provider,
        session=session,
    )


@action("activate_engine_instance")
@permission_required(["system.engine.manage"])
async def activate_engine_instance(ctx: dict[str, Any], session: dict, module_sdk):
    if "engine_id" not in ctx:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t("system.engine.invalid_engine_id"),
                },
            ),
            module_sdk.effects.render(),
        )

    engine_id = int(ctx["engine_id"])
    try:
        engine = module_sdk.models.engine_registry.view(engine_id)
    except Exception:
        engine = None
    if not isinstance(engine, dict):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t("system.engine.invalid_engine_id"),
                },
            ),
            module_sdk.effects.render(),
        )

    activation = await module_sdk.engines.activate_instance(
        engine_registry_id=engine_id,
    )
    if not bool(activation.get("ready")):
        message = str(activation.get("activation_message") or "").strip()
        if not message:
            message = module_sdk.i18n.t("system.engine.activation.not_ready.default")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": message,
                },
            ),
            module_sdk.effects.render(),
        )

    status = str(activation.get("status") or "active").strip().lower() or "active"
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/instance/status": status,
                            "/instance/status_text": module_sdk.i18n.t(
                                f"system.engine.status.{status}"
                            ),
                            "/instance/activation_ready": True,
                            "/instance/activation_message": "",
                        },
                    }
                }
            ]
        ),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success",
                "message": module_sdk.i18n.t("system.engine.activation.activated"),
            },
        ),
        module_sdk.effects.render(),
    )


@action("approve_engine_install")
@permission_required(["system.engine.manage"])
async def approve_engine_install(ctx: dict[str, Any], session: dict, module_sdk):
    if "engine_id" not in ctx:
        return module_sdk.effects.respond(module_sdk.effects.render())

    engine_id = int(ctx["engine_id"])
    try:
        engine = module_sdk.models.engine_registry.view(engine_id)
    except Exception:
        engine = None
    if not isinstance(engine, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())

    provider = str(engine.get("provider") or "").strip().lower()
    requirements = await _provider_requirements(module_sdk, provider)
    if not provider or not bool(requirements.get("supported")):
        return module_sdk.effects.respond(module_sdk.effects.render())

    requirements = await module_sdk.engines.activation_requirements(
        engine_registry_id=engine_id,
    )
    missing_dependencies = [
        dict(item)
        for item in list(requirements.get("missing_dependencies") or [])
        if isinstance(item, dict)
    ]

    for dep in missing_dependencies:
        dep_key = (
            str(dep.get("dependency_key") or "").strip().lower()
            if isinstance(dep, dict)
            else str(dep).strip().lower()
        )
        if not dep_key:
            continue
        module_sdk.access.approve_permanently(
            resource_type=module_sdk.access.EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY,
            operation="execute",
            subject_type="module",
            subject_name=module_sdk.module_name,
            target=f"engine_dependency:{provider}:{dep_key}",
        )

    task_effects = await start_engine_install_task(
        module_sdk,
        engine_id=engine_id,
        provider=provider,
        session=session,
        on_finish={
            "name": "nav",
            "context": {
                "type": "nav",
                "path": f"/system/engine/provider/{provider}",
            },
        },
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "modal"}}]),
        *task_effects,
    )


@action("deactivate_engine")
@permission_required(["system.engine.manage"])
async def deactivate_engine(ctx: dict[str, Any], session: dict, module_sdk):
    if "engine_id" not in ctx:
        return module_sdk.effects.respond(module_sdk.effects.render())
    engine_id = int(ctx["engine_id"])
    provider = str(ctx["provider"]).strip().lower() if "provider" in ctx else ""
    try:
        deactivation = await module_sdk.engines.deactivate_instance(
            engine_registry_id=engine_id,
        )
    except Exception as exc:
        module_sdk.system.log(
            f"[engine.activation] deactivate failed engine_id={engine_id}: {exc}",
            "error",
        )
        deactivation = {}
    if not bool(deactivation.get("ready")):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t("system.engine.invalid_engine_id"),
                },
            ),
            module_sdk.effects.render(),
        )
    status = str(deactivation.get("status") or "installed").strip().lower()
    if provider:
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                [
                    page_state_update(
                        provider_store_values(
                            module_sdk,
                            provider=provider,
                            status=status,
                        )
                    )
                ]
            ),
            module_sdk.effects.render(),
        )
    return module_sdk.effects.respond(module_sdk.effects.render())


@action("close_engine_install_modal")
@permission_required(["system.engine.manage"])
async def close_engine_install_modal(ctx: dict[str, Any], session: dict, module_sdk):
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "modal"}}]),
        module_sdk.effects.render(),
    )


@action("engine_not_supported")
@permission_required(["system.engine.view"])
async def engine_not_supported(ctx: dict[str, Any], session: dict, module_sdk):
    return module_sdk.effects.respond(module_sdk.effects.render())
