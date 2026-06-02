from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action

from . import ai_chat as _ai_chat_actions  # noqa: F401
from . import ai_input as _ai_input_actions  # noqa: F401
from . import calendar as _calendar_actions  # noqa: F401
from . import code_diff as _code_diff_actions  # noqa: F401
from . import grid as _grid_actions  # noqa: F401
from . import select as _select_actions  # noqa: F401
from . import showcase as _showcase_actions  # noqa: F401
from . import wizard as _wizard_actions  # noqa: F401
from . import yaml as _yaml_actions  # noqa: F401


@action("form_preview_show_value")
@permission_required(["components.documentation.view"])
async def form_preview_show_value(ctx: dict, sdk) -> dict:
    field_ids = ctx.get("field_ids")
    if isinstance(field_ids, list) and field_ids:
        label = str(ctx.get("label") or "form").strip() or "form"
        payload: dict[str, object] = {}
        for field_id in field_ids:
            key = str(field_id or "").strip()
            if key:
                payload[key] = ctx.get(key)

        rendered_value = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(rendered_value) > 700:
            rendered_value = f"{rendered_value[:700]}..."

        return sdk.effects.respond(
            sdk.effects.notify(
                "toast",
                {
                    "title": f"{label} values",
                    "text": rendered_value,
                    "variant": "info",
                    "duration": 3600,
                },
            )
        )

    input_id = str(ctx.get("input_id") or "").strip()
    label = str(ctx.get("label") or input_id or "input").strip() or "input"
    raw_value = ctx.get(input_id) if input_id and input_id in ctx else ctx.get("value")

    if raw_value in (None, "", []):
        rendered_value = "(empty)"
    elif isinstance(raw_value, (dict, list, tuple, bool, int, float)):
        try:
            rendered_value = json.dumps(raw_value, ensure_ascii=False)
        except Exception:
            rendered_value = str(raw_value)
    else:
        rendered_value = str(raw_value)

    if len(rendered_value) > 700:
        rendered_value = f"{rendered_value[:700]}..."

    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": f"{label} value",
                "text": rendered_value,
                "variant": "info",
                "duration": 3400,
            },
        )
    )
