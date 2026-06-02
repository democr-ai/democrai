from .layout import shell_layout
from democrai.sdk.client import active_sdk as sdk


async def render(params: dict, session: dict) -> None:
    builder = sdk.ui.Builder()
    await shell_layout(builder)
    return builder
