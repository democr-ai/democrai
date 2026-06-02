from democrai.sdk.auth import permission_required
from .layout import shell_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(params: dict, session: dict) -> None:
    builder = sdk.ui.Builder()
    await shell_layout(builder)
    return builder
