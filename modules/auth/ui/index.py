from typing import Any, Dict
from democrai.sdk.decorators import public, template
from democrai.sdk.client import active_sdk as sdk


@template("empty")
@public
async def render(params: Dict[str, Any], session: dict) -> Any:
    builder = sdk.ui.load("utils/ui/yaml/logout")
    return builder
