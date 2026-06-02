from __future__ import annotations

from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.utils.actions.knowledge.extractors import (
    extractor_install_in_progress,
    start_extractor_install_task,
    start_extractor_test_task,
)


def _extractor_row(module_sdk, extractor_id: str) -> dict[str, Any] | None:
    rows = module_sdk.models.extractor_registry.list(
        page=0,
        page_size=1,
        filters={"extractor_id": extractor_id},
    ).get("rows") or []
    row = rows[0] if rows else None
    return row if isinstance(row, dict) else None


def _first_form_upload(ctx: dict[str, Any]) -> dict[str, Any]:
    form = ctx.get("knowledge_extractor_test_form")
    if not isinstance(form, dict):
        return {}
    document = form.get("document")
    if isinstance(document, list) and document and isinstance(document[0], dict):
        return dict(document[0])
    if isinstance(document, dict):
        return dict(document)
    return {}


def _extractor_config_form(ctx: dict[str, Any], phase: str) -> dict[str, Any]:
    form_id = (
        "knowledge_extractor_install_config_form"
        if phase == "install"
        else "knowledge_extractor_runtime_config_form"
    )
    form = ctx.get(form_id)
    return dict(form) if isinstance(form, dict) else {}


def _t(module_sdk, key: str, context: dict[str, Any] | None = None) -> str:
    return module_sdk.i18n.t(key, context=context or {})


@action("install_extractor")
@permission_required(["system.knowledge.extractor.manage"])
async def install_extractor(ctx: dict[str, Any], session: dict, module_sdk):
    extractor_id = str(ctx["extractor_id"]).strip().lower()
    row = _extractor_row(module_sdk, extractor_id)
    if not isinstance(row, dict):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": _t(
                        module_sdk,
                        "system.knowledge.extractors.toast.registry_missing",
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    extractor_row_id = int(row["id"])
    current_status = str(row.get("status") or "").strip().lower()
    if (
        current_status == "installing"
        or extractor_install_in_progress(module_sdk, extractor_id)
    ):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "info",
                    "message": _t(
                        module_sdk,
                        "system.knowledge.extractors.toast.install_running",
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    if current_status not in {"uninstalled", "error"}:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "info",
                    "message": _t(
                        module_sdk,
                        "system.knowledge.extractors.toast.status",
                        {"status": current_status or "unknown"},
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    update_payload: dict[str, Any] = {"status": "installing", "supported": True}
    install_form = ctx.get("knowledge_extractor_install_config_form")
    if isinstance(install_form, dict):
        update_payload["install_config"] = dict(install_form)
    module_sdk.models.extractor_registry.update(extractor_row_id, update_payload)
    await start_extractor_install_task(
        module_sdk,
        extractor_row_id=extractor_row_id,
        extractor_id=extractor_id,
        session=session,
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "modal"}}]),
        module_sdk.effects.render(),
    )


@action("save_extractor_config")
@permission_required(["system.knowledge.extractor.manage"])
async def save_extractor_config(ctx: dict[str, Any], session: dict, module_sdk):
    extractor_id = str(ctx["extractor_id"]).strip().lower()
    phase = str(ctx.get("phase") or "runtime").strip().lower()
    if phase not in {"install", "runtime"}:
        raise ValueError(f"extractor_config_phase_invalid:{phase}")

    row = _extractor_row(module_sdk, extractor_id)
    if not isinstance(row, dict):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": _t(
                        module_sdk,
                        "system.knowledge.extractors.toast.registry_missing",
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    payload = _extractor_config_form(ctx, phase)
    update_key = "install_config" if phase == "install" else "config"
    module_sdk.models.extractor_registry.update(int(row["id"]), {update_key: payload})
    return module_sdk.effects.respond(
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success",
                "message": _t(
                    module_sdk,
                    "system.knowledge.extractors.toast.config_saved",
                ),
            },
        ),
        module_sdk.effects.render(),
    )


@action("set_extractor_mime_binding")
@permission_required(["system.knowledge.extractor.manage"])
async def set_extractor_mime_binding(ctx: dict[str, Any], session: dict, module_sdk):
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else ctx.get("row_data")
    row_data = dict(row) if isinstance(row, dict) else {}
    mime_type = str(
        row_data.get("mime_type")
        or ctx.get("mime_type")
        or ctx.get("rowId")
        or ctx.get("row_id")
        or ""
    ).strip().lower()
    extractor_id = str(
        ctx.get("value")
        if "value" in ctx
        else ctx.get("new_value") if "new_value" in ctx else ""
    ).strip().lower()
    if not mime_type:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": _t(
                        module_sdk,
                        "system.knowledge.extractor_config.toast.mime_required",
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    try:
        module_sdk.extractors.set_mime_type_binding(
            mime_type=mime_type,
            extractor_id=extractor_id,
        )
    except ValueError as exc:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": str(exc)},
            ),
            module_sdk.effects.render(),
        )

    message = (
        _t(module_sdk, "system.knowledge.extractor_config.toast.binding_removed")
        if not extractor_id
        else _t(module_sdk, "system.knowledge.extractor_config.toast.binding_saved")
    )
    return module_sdk.effects.respond(
        module_sdk.effects.notify(
            "toast",
            {"level": "success", "message": message},
        ),
        module_sdk.effects.render(),
    )


@action("test_extractor_document")
@permission_required(["system.knowledge.extractor.manage"])
async def test_extractor_document(ctx: dict[str, Any], session: dict, module_sdk):
    extractor_id = str(ctx["extractor_id"]).strip().lower()
    if not extractor_id:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": _t(
                        module_sdk,
                        "system.knowledge.extractor_detail.toast.extractor_required",
                    ),
                },
            )
        )

    upload = _first_form_upload(ctx)
    storage_path = str(upload.get("storage_path") or upload.get("path") or "").strip()
    if not storage_path:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": _t(
                        module_sdk,
                        "system.knowledge.extractor_detail.select_document",
                    ),
                },
            )
        )

    filename = str(upload.get("name") or upload.get("filename") or "").strip()
    mime_type = str(
        upload.get("mime") or upload.get("type") or upload.get("content_type") or ""
    ).strip()
    return module_sdk.effects.respond(
        *(
            await start_extractor_test_task(
                module_sdk,
                extractor_id=extractor_id,
                upload=upload,
                storage_path=storage_path,
                filename=filename,
                mime_type=mime_type,
            )
        )
    )


@action("show_extractor_test_result")
@permission_required(["system.knowledge.extractor.manage"])
async def show_extractor_test_result(ctx: dict[str, Any], session: dict, module_sdk):
    result = ctx.get("result")
    payload = result if isinstance(result, dict) else {}
    result_markdown = str(payload.get("result_markdown") or "").strip()
    if not result_markdown:
        result_markdown = module_sdk.i18n.t(
            "system.knowledge.extractor_test.empty_result_markdown"
        )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "knowledge_extractor_test_result",
            "text",
            result_markdown,
        )
    )


@action("show_extractor_test_error")
@permission_required(["system.knowledge.extractor.manage"])
async def show_extractor_test_error(ctx: dict[str, Any], session: dict, module_sdk):
    error = str(
        ctx.get("error")
        or module_sdk.i18n.t("system.knowledge.extractor_test.failed")
    ).strip()
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "knowledge_extractor_test_result",
            "text",
            module_sdk.i18n.t(
                "system.knowledge.extractor_test.failed_markdown",
                context={"error": error},
            ),
        )
    )
