from typing import Any, Dict
from democrai.sdk.decorators import only_guest, public, render_hook_slot, template
from democrai.sdk.client import active_sdk as sdk


@render_hook_slot(
    "login.form.after_fields",
    optional=True,
    description="Inject additional UI components after the login form fields.",
)
def register_login_form_after_fields_hook():
    return None


@template("empty")
@only_guest
@public
async def render(params: Dict[str, Any], session: dict) -> Any:
    builder = sdk.ui.load("utils/ui/yaml/login")
    return builder
