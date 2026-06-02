from typing import Any
from typing import Dict

from democrai.sdk.decorators import public
from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.decorators import template
from democrai.sdk.system import AccessDeniedError


@template("empty")
@public
async def render(params: Dict[str, Any], session: dict) -> sdk.ui.Builder:
    if not sdk.system.setup.is_enabled():
        raise AccessDeniedError(
            "Setup has already been completed or the application is already installed."
        )

    builder = sdk.ui.load("utils/ui/yaml/setup/wizard")
    builder.set_store("/system/setup/step", 1, scope="page")
    builder.set_store("/system/setup/install_mode", "local", scope="page")
    builder.set_store("/system/setup/media_path", "", scope="page")
    builder.set_store("/system/setup/admin_user", "admin", scope="page")
    builder.set_store("/system/setup/admin_email", "admin@democr.ai", scope="page")
    builder.set_store("/system/setup/config_upload", None, scope="page")
    builder.set_store("/system/setup/config_upload_value", [], scope="page")
    builder.set_store("/system/setup/template_export_message", "", scope="page")
    builder.set_store("/system/setup/config_validated", False, scope="page")
    builder.set_store("/system/setup/config_validation_errors", [], scope="page")
    builder.set_store("/system/setup/config_validation_warnings", [], scope="page")
    builder.set_store("/system/setup/distributed_config_payload", {}, scope="page")
    builder.set_store(
        "/system/setup/config_validation_status",
        "No YAML file selected.",
        scope="page",
    )
    builder.set_store(
        "/system/setup/title",
        "Democrai Setup - Step 1/3",
        scope="page",
    )
    builder.set_store("/system/setup/step_label", "Step 1/3", scope="page")
    builder.set_store("/system/setup/progress_value", 33, scope="page")
    builder.set_store(
        "/system/setup/mode_summary",
        "Current mode: Local",
        scope="page",
    )
    return builder
