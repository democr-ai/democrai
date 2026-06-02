from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


def _state_update(sdk, scope: str, values: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages([{"stateUpdate": {"scope": scope, "values": values}}])
    )


def _data_update(sdk, surface_id: str, data: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [sdk.ui.Builder.build_data_model_update_payload(surface_id=surface_id, data=data)]
        )
    )


_UPDATED_HUNKS = [
    {
        "old_start": 42,
        "new_start": 42,
        "header": "@@ -42,5 +42,6 @@",
        "lines": [
            {"type": "context", "old_no": 42, "new_no": 42, "text": "def validate(payload):"},
            {"type": "remove", "old_no": 43, "text": "    return payload is not None"},
            {"type": "add", "new_no": 43, "text": "    if payload is None:"},
            {"type": "add", "new_no": 44, "text": "        return False"},
            {"type": "context", "old_no": 44, "new_no": 45, "text": "    return bool(payload)"},
        ],
    }
]


_UPDATED_MODEL = {
    "title": "Runtime guard fix",
    "filePath": "modules/core/logic.py",
    "oldRevision": "a31f9e2",
    "newRevision": "c9bbd51",
    "showLineNumbers": False,
    "hunks": _UPDATED_HUNKS,
}


@action("codediff_update")
@permission_required(["components.documentation.view"])
async def codediff_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_complex/codediff/title": _UPDATED_MODEL["title"],
                "/components_complex/codediff/filePath": _UPDATED_MODEL["filePath"],
                "/components_complex/codediff/oldRevision": _UPDATED_MODEL["oldRevision"],
                "/components_complex/codediff/newRevision": _UPDATED_MODEL["newRevision"],
                "/components_complex/codediff/showLineNumbers": _UPDATED_MODEL["showLineNumbers"],
                "/components_complex/codediff/hunks": _UPDATED_MODEL["hunks"],
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_complex/codediff/title": _UPDATED_MODEL["title"],
                "/components_complex/codediff/filePath": _UPDATED_MODEL["filePath"],
                "/components_complex/codediff/oldRevision": _UPDATED_MODEL["oldRevision"],
                "/components_complex/codediff/newRevision": _UPDATED_MODEL["newRevision"],
                "/components_complex/codediff/showLineNumbers": _UPDATED_MODEL["showLineNumbers"],
                "/components_complex/codediff/hunks": _UPDATED_MODEL["hunks"],
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_complex": {"codediff_model": _UPDATED_MODEL}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_codediff_direct",
                "title",
                _UPDATED_MODEL["title"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_codediff_direct",
                "filePath",
                _UPDATED_MODEL["filePath"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_codediff_direct",
                "oldRevision",
                _UPDATED_MODEL["oldRevision"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_codediff_direct",
                "newRevision",
                _UPDATED_MODEL["newRevision"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_codediff_direct",
                "showLineNumbers",
                _UPDATED_MODEL["showLineNumbers"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_codediff_direct",
                "hunks",
                _UPDATED_MODEL["hunks"],
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
