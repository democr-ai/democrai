from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from democrai.sdk.system import to_optional_int

from modules.system.utils.actions.engine.providers import (
    dependency_labels,
    drain_engine_install_output,
    emit_engine_install_output_progress,
    subscribe_engine_install_output,
    unsubscribe_engine_install_output,
)
from modules.system.utils.actions.engine.store import (
    page_state_update,
    provider_store_values,
)


async def runtime_config_ready_for_activation(
    module_sdk,
    *,
    provider: str,
    engine: dict[str, Any] | None,
) -> dict[str, Any]:
    config = (
        engine.get("config")
        if isinstance(engine, dict) and isinstance(engine.get("config"), dict)
        else {}
    )
    try:
        result = await module_sdk.engines.check_runtime_config(
            engine_id=provider,
            config=config,
        )
    except Exception as exc:
        module_sdk.system.log(
            (
                "[engine.activation] runtime config validation failed "
                f"provider={provider} error={exc}"
            ),
            "error",
        )
        return {
            "ready": False,
            "missing_config": [],
            "message": str(exc),
        }
    payload = dict(result or {})
    payload.setdefault("ready", True)
    payload.setdefault("missing_config", [])
    payload.setdefault("message", "")
    return payload


def render_install_modal(
    module_sdk,
    *,
    engine_id: int,
    provider: str,
    provider_name: str,
    missing_dependencies: list[dict[str, str]],
    status_text: str,
    installing: bool = False,
    done: bool = False,
):
    dep_labels = dependency_labels(missing_dependencies)
    dependencies_text = ", ".join(dep_labels) or module_sdk.i18n.t(
        "system.engine.activation.missing.none"
    )

    builder = module_sdk.ui.load("utils/ui/yaml/engine/modals/engine_install")

    dialog = builder.get_component("engine_install_dialog")
    if dialog is not None:
        dialog.set_property(
            "title",
            module_sdk.i18n.t(
                "system.engine.activation.modal.title",
                context={"provider": provider_name},
            ),
        )

    deps = builder.get_component("engine_install_dependencies")
    if deps is not None:
        deps.set_property(
            "text",
            module_sdk.i18n.t(
                "system.engine.activation.modal.dependencies",
                context={"provider": provider_name, "dependencies": dependencies_text},
            ),
        )

    progress = builder.get_component("engine_install_progress")
    if progress is not None:
        progress.set_property("value", 100 if done else 0)

    status = builder.get_component("engine_install_status")
    if status is not None:
        status.set_property("text", status_text)

    footer = builder.get_component("engine_install_footer")
    if footer is not None and done:
        footer.set_children(["engine_install_close_btn"])

    approve_btn = builder.get_component("engine_install_approve_btn")
    if approve_btn is not None:
        approve_btn.set_property("params", {"engine_id": engine_id})
        if installing or done:
            approve_btn.set_property("disabled", True)

    close_btn = builder.get_component("engine_install_close_btn")
    if close_btn is not None and installing:
        close_btn.set_property("disabled", True)

    return builder


async def publish_install_progress(
    module_sdk,
    *,
    stream_id: str | None,
    engine_id: int,
    value: int | None = None,
    status_text: str | None = None,
):
    if not stream_id:
        return
    if value is not None:
        await module_sdk.effects.publish_property_update(
            stream_id,
            "engine_install_progress",
            "value",
            max(0, min(100, int(value))),
            surface_id="modal",
        )
    if status_text is not None:
        await module_sdk.effects.publish_property_update(
            stream_id,
            "engine_install_status",
            "text",
            status_text,
            surface_id="modal",
        )


async def publish_install_modal_state(
    module_sdk,
    *,
    stream_id: str | None,
    engine_id: int,
    close_disabled: bool,
):
    if not stream_id:
        return
    await module_sdk.effects.publish_property_update(
        stream_id,
        "engine_install_close_btn",
        "disabled",
        bool(close_disabled),
        surface_id="modal",
    )


async def publish_engine_activated_ui(
    module_sdk,
    *,
    stream_id: str | None,
    provider: str,
    engine_id: int,
):
    """Push UI updates after an engine has been activated.

    Updates the page store `/provider/*` so the provider page reacts
    reactively, then closes the install modal. The list page refreshes its
    cards on next render — no per-card patching here.
    """
    if not stream_id:
        return
    await module_sdk.effects.publish_ui_message(
        stream_id,
        page_state_update(
            provider_store_values(
                module_sdk,
                provider=provider,
                status="active",
                activation_ready=True,
                activation_message="",
            )
        ),
    )
    await module_sdk.effects.publish_ui_message(
        stream_id,
        {"deleteSurface": {"surfaceId": "modal"}},
    )


async def run_engine_install_background(
    module_sdk,
    *,
    task_ref: dict[str, str],
    engine_row_id: int,
    provider: str,
    force: bool,
    requested_by: dict[str, Any],
) -> dict[str, Any]:
    from modules.system.utils.actions.engine.config import provider_display_name

    while not str(task_ref.get("task_id") or "").strip():
        await asyncio.sleep(0.05)

    task_id = str(task_ref.get("task_id") or "").strip()
    provider_name = provider_display_name(module_sdk, provider)
    module_sdk.system.log(
        "[system.engine] background install start "
        f"provider={provider} engine_row_id={engine_row_id} task_id={task_id}",
        "info",
    )
    await module_sdk.tasks.update_progress(task_id, 0.05, label=provider_name)

    output_queue = subscribe_engine_install_output(module_sdk)
    try:
        await module_sdk.tasks.update_progress(
            task_id,
            0.10,
            label="Preparing engine installation",
        )
        install_result = await module_sdk.engines.begin_install(
            engine_registry_id=engine_row_id,
            force=force,
            requested_by=requested_by,
            task_id=task_id,
        )
        install_event = dict((install_result or {}).get("event") or {})
        event_id = str((install_event or {}).get("event_id") or "").strip()
        module_sdk.system.log(
            "[system.engine] install requested "
            f"provider={provider} engine_row_id={engine_row_id} "
            f"task_id={task_id} event_id={event_id or 'missing'}",
            "info",
        )
        await module_sdk.tasks.update_progress(
            task_id,
            0.15,
            label="Installing engine dependencies",
        )

        provider_definition = await module_sdk.engines.get_provider_definition(
            provider_id=provider
        )
        install_timeout_seconds = float(
            (provider_definition or {}).get("install_timeout_seconds") or 600.0
        )
        deadline = asyncio.get_running_loop().time() + max(
            600.0,
            install_timeout_seconds,
        )
        last_status = ""
        last_live_emit = 0.0
        while True:
            now = asyncio.get_running_loop().time()
            latest_output = drain_engine_install_output(output_queue, event_id=event_id)
            if latest_output and now - last_live_emit >= 0.5:
                await emit_engine_install_output_progress(
                    module_sdk,
                    task_id=task_id,
                    progress=0.6,
                    payload=latest_output,
                )
                last_live_emit = now

            listing = module_sdk.models.engine_node_install_registry.list(
                page=0,
                page_size=20,
                filters={
                    "engine_id": provider,
                    **({("last_event_id"): event_id} if event_id else {}),
                },
                sort={"field": "updated_at", "direction": "desc"},
            )
            rows = listing.get("rows") or []
            node_row = rows[0] if rows else {}
            status = str(node_row.get("status") or "").strip().lower()
            last_error = str(node_row.get("last_error") or "").strip()

            if status == "installing":
                if status != last_status:
                    await module_sdk.tasks.update_progress(
                        task_id,
                        0.6,
                        label="Installing engine runtime",
                    )
            elif status == "installed":
                await module_sdk.tasks.update_progress(
                    task_id,
                    1.0,
                    label="Engine installed",
                )
                return {
                    "engine_id": engine_row_id,
                    "provider": provider,
                    "status": "installed",
                }
            elif status == "error":
                raise RuntimeError(last_error or f"{provider} install failed")
            last_status = status

            if now >= deadline:
                raise TimeoutError(f"{provider} install timed out")

            await asyncio.sleep(0.25)
    finally:
        with suppress(Exception):
            unsubscribe_engine_install_output(module_sdk, output_queue)


async def start_engine_install_task(
    module_sdk,
    *,
    engine_id: int,
    provider: str,
    force: bool = False,
    session: dict[str, Any],
    mount_id: str | None = None,
    card_id_prefix: str = "engine_install_task",
    on_finish: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from modules.system.utils.actions.engine.config import provider_display_name
    from modules.system.utils.actions.engine.constants import (
        _ENGINE_PROVIDER_TASK_MOUNT_ID,
    )

    task_ref = {"task_id": ""}
    task_label = module_sdk.i18n.t(
        "system.engine.install.task.label",
        context={"provider": provider_display_name(module_sdk, provider)},
    )
    user = session.get("user") if isinstance(session.get("user"), dict) else {}
    requested_by = {
        "user_id": to_optional_int(user.get("id")),
        "organization_id": to_optional_int(user.get("organization_id")),
    }
    task_id = await module_sdk.tasks.run_background(
        run_engine_install_background(
            module_sdk,
            task_ref=task_ref,
            engine_row_id=engine_id,
            provider=provider,
            force=force,
            requested_by=requested_by,
        ),
        label=task_label,
        task_key=f"system.engine.install.{provider}.{engine_id}",
    )
    task_ref["task_id"] = task_id
    card_kwargs: dict[str, Any] = {"task_id": task_id}
    if on_finish is not None:
        card_kwargs["on_finish"] = on_finish
    card = module_sdk.ui.BackgroundTask(
        f"{card_id_prefix}_{engine_id}_{task_id}",
        **card_kwargs,
    )
    return [
        module_sdk.effects.ui_collection_append(
            mount_id or _ENGINE_PROVIDER_TASK_MOUNT_ID,
            "children",
            card.to_dict(),
        )
    ]
