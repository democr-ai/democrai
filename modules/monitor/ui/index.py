from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk


@permission_required(["monitor.view"])
async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/index")

    return builder
