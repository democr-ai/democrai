from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from democrai.sdk.decorators import action, setup_only, validate

from modules.system.utils.actions.setup import validate_distributed_config

SETUP_STEPS = 3


class SetupStepPayload(BaseModel):
    step: int = Field(default=1, ge=1, le=SETUP_STEPS)
    stream_id: str | None = None


class SetupNextPayload(SetupStepPayload):
    install_mode: Literal["local", "distributed"] | None = None
    config_attachment_input: list[dict[str, Any]] | None = None
    media_path_input: str = ""


class SetupConfigValidationPayload(BaseModel):
    config_attachment_input: list[dict[str, Any]] | None = None


class SetupTemplateExportPayload(BaseModel):
    template_name: Literal["local", "distributed"] = "distributed"


class SetupFinishPayload(BaseModel):
    stream_id: str | None = None
    session_key: str | None = None
    admin_user: str = Field(default="admin", min_length=1)
    admin_email: str = ""
    admin_pass: str = Field(min_length=1)

    @field_validator("admin_user", "admin_pass")
    @classmethod
    def _required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("value is required")
        return text


def _step_values(step: int, install_mode: str | None = None) -> dict[str, Any]:
    resolved_step = max(1, min(SETUP_STEPS, int(step or 1)))
    values: dict[str, Any] = {
        "/system/setup/step": resolved_step,
        "/system/setup/title": f"Democrai Setup - Step {resolved_step}/{SETUP_STEPS}",
        "/system/setup/step_label": f"Step {resolved_step}/{SETUP_STEPS}",
        "/system/setup/progress_value": int(resolved_step / SETUP_STEPS * 100),
    }
    if install_mode:
        label = "Distributed" if install_mode == "distributed" else "Local"
        values["/system/setup/mode_summary"] = f"Current mode: {label}"
    return values


def _state_update(module_sdk, values: dict[str, Any]) -> dict[str, Any]:
    return module_sdk.effects.ui_messages(
        [
            module_sdk.ui.Builder.build_state_update_payload(
                values,
                scope="page",
            )
        ]
    )


def _validation_clear_values() -> dict[str, Any]:
    return {
        "/system/setup/distributed_config_payload": {},
        "/system/setup/config_validated": False,
        "/system/setup/config_validation_errors": [],
        "/system/setup/config_validation_warnings": [],
        "/system/setup/config_validation_status": "No YAML file selected.",
        "/system/setup/config_upload": None,
        "/system/setup/config_upload_value": [],
    }


async def _store_value(
    module_sdk,
    path: str,
    *,
    stream_id: str | None = None,
    default: Any = None,
) -> Any:
    value = await module_sdk.effects.ask_current_store_value(
        stream_id,
        path,
        store_type="page",
    )
    return default if value is None else value


@action("setup_next")
@validate(SetupNextPayload, strip_extra=True)
@setup_only
async def setup_next(ctx: dict[str, Any], session: dict, module_sdk):
    curr = ctx["step"]
    stream_id = ctx.get("stream_id")
    state_values: dict[str, Any] = {}

    if curr == 1:
        install_mode = ctx.get("install_mode") or "local"
        state_values["/system/setup/install_mode"] = install_mode
        state_values["/system/setup/template_export_message"] = ""
        state_values.update(_validation_clear_values())
        state_values.update(_step_values(2, install_mode))
        return module_sdk.effects.respond(_state_update(module_sdk, state_values))

    if curr == 2:
        install_mode = str(
            await _store_value(
                module_sdk,
                "/system/setup/install_mode",
                stream_id=stream_id,
                default="local",
            )
        )
        if install_mode == "distributed":
            upload_items = ctx.get("config_attachment_input")
            upload_item = (
                upload_items[0]
                if isinstance(upload_items, list) and upload_items
                else None
            )
            state_values["/system/setup/config_upload"] = upload_item
            state_values["/system/setup/config_upload_value"] = (
                [upload_item] if isinstance(upload_item, dict) else []
            )
            state_values["/system/setup/template_export_message"] = ""
            ok = await validate_distributed_config(
                module_sdk,
                upload_item=upload_item,
                state_values=state_values,
            )
            if not ok:
                state_values.update(_step_values(2, install_mode))
                return module_sdk.effects.respond(
                    _state_update(module_sdk, state_values)
                )
        else:
            media_path = ctx["media_path_input"].strip()
            state_values["/system/setup/media_path"] = media_path
            state_values.update(_validation_clear_values())

        state_values.update(_step_values(3, install_mode))
        return module_sdk.effects.respond(_state_update(module_sdk, state_values))

    next_step = min(SETUP_STEPS, curr + 1)
    state_values.update(_step_values(next_step))
    return module_sdk.effects.respond(_state_update(module_sdk, state_values))


@action("setup_prev")
@validate(SetupStepPayload, strip_extra=True)
@setup_only
async def setup_prev(ctx: dict[str, Any], session: dict, module_sdk):
    curr = ctx["step"]
    stream_id = ctx.get("stream_id")
    install_mode = await _store_value(
        module_sdk,
        "/system/setup/install_mode",
        stream_id=stream_id,
        default="local",
    )
    prev_step = max(1, curr - 1)
    return module_sdk.effects.respond(
        _state_update(
            module_sdk,
            _step_values(prev_step, str(install_mode or "local")),
        )
    )


@action("validate_setup_config")
@validate(SetupConfigValidationPayload, strip_extra=True)
@setup_only
async def validate_setup_config(ctx: dict[str, Any], session: dict, module_sdk):
    upload_items = ctx.get("config_attachment_input")
    upload_item = (
        upload_items[0]
        if isinstance(upload_items, list) and upload_items
        else None
    )
    state_values: dict[str, Any] = {"/system/setup/config_upload": upload_item}
    state_values["/system/setup/config_upload_value"] = (
        [upload_item] if isinstance(upload_item, dict) else []
    )
    await validate_distributed_config(
        module_sdk,
        upload_item=upload_item,
        state_values=state_values,
    )
    return module_sdk.effects.respond(_state_update(module_sdk, state_values))


@action("export_setup_template")
@validate(SetupTemplateExportPayload, strip_extra=True)
@setup_only
async def export_setup_template(ctx: dict[str, Any], session: dict, module_sdk):
    template_name = ctx["template_name"]
    asset_name = (
        "config.example.yaml"
        if template_name == "local"
        else "config.distributed.example.yaml"
    )
    public_url = str(
        module_sdk.media.get_public_url(f"assets/{asset_name}") or ""
    ).strip()
    return module_sdk.effects.respond(
        module_sdk.effects.open_url(
            public_url,
            download=True,
            filename=asset_name,
        )
    )


@action("setup_finish")
@validate(SetupFinishPayload, strip_extra=True)
@setup_only
async def setup_finish(ctx: dict[str, Any], session: dict, module_sdk):
    from modules.system.utils.actions.setup import finalize_setup

    stream_id = ctx.get("stream_id") or None
    session_key = ctx.get("session_key") or None
    admin_user = ctx["admin_user"]
    admin_email = ctx["admin_email"].strip()
    admin_pass = ctx["admin_pass"]
    install_mode = str(
        await _store_value(
            module_sdk,
            "/system/setup/install_mode",
            stream_id=stream_id,
            default="local",
        )
    )
    payload = None
    media_path = None
    if install_mode == "distributed":
        payload = await _store_value(
            module_sdk,
            "/system/setup/distributed_config_payload",
            stream_id=stream_id,
            default={},
        )
    else:
        media_path = str(
            await _store_value(
                module_sdk,
                "/system/setup/media_path",
                stream_id=stream_id,
                default="",
            )
        )

    try:
        await finalize_setup(
            module_sdk,
            install_mode=install_mode,
            admin_user=admin_user,
            admin_email=admin_email,
            admin_pass=admin_pass,
            payload=payload if isinstance(payload, dict) else None,
            media_path=media_path,
            stream_id=stream_id,
            session_key=session_key,
        )
    except Exception as exc:
        module_sdk.system.log(f"[Setup] Finalization failed: {exc}", "error")
        return {
            "ok": False,
            "type": "error",
            "error": "setup_finalize_failed",
            "details": str(exc),
        }

    return module_sdk.effects.respond()
