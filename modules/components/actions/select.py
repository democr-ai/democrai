from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action, validate
from pydantic import BaseModel


class SelectPopulateActionPayload(BaseModel):
    target: str = "action_select_dynamic"


class SelectPopulateStatePayload(BaseModel):
    pass


@action("select_preview_populate_action")
@validate(SelectPopulateActionPayload, strip_extra=True)
@permission_required(["components.documentation.view"])
async def select_preview_populate_action(ctx: dict, session: dict, sdk) -> dict:
    target = ctx["target"]
    options = [
        {"label": "Italy", "value": "it"},
        {"label": "Spain", "value": "es"},
        {"label": "France", "value": "fr"},
        {"label": "Germany", "value": "de"},
    ]
    return sdk.effects.respond(
        sdk.effects.ui_property_update(target, "options", options),
        sdk.effects.ui_property_update(target, "value", ""),
        sdk.effects.notify(
            "toast",
            {
                "title": "Select options updated",
                "text": f"Loaded {len(options)} options via action.",
                "variant": "success",
                "duration": 2400,
            },
        ),
    )


@action("select_preview_populate_state")
@validate(SelectPopulateStatePayload, strip_extra=True)
@permission_required(["components.documentation.view"])
async def select_preview_populate_state(ctx: dict, session: dict, sdk) -> dict:
    values = [
        {"label": "Backlog", "value": "backlog"},
        {"label": "In Progress", "value": "in_progress"},
        {"label": "In Review", "value": "in_review"},
        {"label": "Done", "value": "done"},
    ]
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {"select_state_options": values},
                    }
                }
            ]
        ),
        sdk.effects.notify(
            "toast",
            {
                "title": "State updated",
                "text": "Options loaded into page state.",
                "variant": "info",
                "duration": 2400,
            },
        ),
    )
