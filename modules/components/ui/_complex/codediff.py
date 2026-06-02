from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_HUNKS = [
    {
        "old_start": 12,
        "new_start": 12,
        "header": "@@ -12,6 +12,7 @@",
        "lines": [
            {"type": "context", "old_no": 12, "new_no": 12, "text": "server:"},
            {"type": "remove", "old_no": 13, "text": "  timeout: 30s"},
            {"type": "add", "new_no": 13, "text": "  timeout: 60s"},
            {"type": "add", "new_no": 14, "text": "  retry_attempts: 3"},
            {"type": "context", "old_no": 14, "new_no": 15, "text": "  logging: info"},
        ],
    }
]

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


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/code_diff"), components=True)

    for scope in ("page", "global"):
        builder.set_store("/components_complex/codediff/title", "Configuration update", scope=scope)
        builder.set_store("/components_complex/codediff/filePath", "config/settings.yaml", scope=scope)
        builder.set_store("/components_complex/codediff/oldRevision", "7f8e9a2", scope=scope)
        builder.set_store("/components_complex/codediff/newRevision", "4b2c1d0", scope=scope)
        builder.set_store("/components_complex/codediff/showLineNumbers", True, scope=scope)
        builder.set_store("/components_complex/codediff/hunks", _HUNKS, scope=scope)

    builder.set_data(
        "/components_complex/codediff_model",
        {
            "title": "Configuration update",
            "filePath": "config/settings.yaml",
            "oldRevision": "7f8e9a2",
            "newRevision": "4b2c1d0",
            "showLineNumbers": True,
            "hunks": _HUNKS,
        },
    )
    builder.set_data(
        "/components_complex/codediff_bindings",
        [
            {"binding": "Literal", "yaml": "hunks:\n  - header: '@@ -12,6 +12,7 @@'", "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "hunks: {type: store, scope: page, path: /components_complex/codediff/hunks}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "hunks: {type: store, scope: global, path: /components_complex/codediff/hunks}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": 'hunks: "@data/components_complex/codediff_model/hunks"', "source": "builder.set_data(...)"},
            {"binding": "Direct update", "yaml": "capabilities: [title.set, filePath.set, hunks.set]", "source": "sdk.effects.ui_property_update(...)"},
        ],
    )
    builder.set_data(
        "/components_complex/codediff_properties",
        [
            {"property": "title", "type": "str", "usage": sdk.i18n.t("components.complex.codediff.property.title")},
            {"property": "filePath", "type": "str", "usage": sdk.i18n.t("components.complex.codediff.property.file_path")},
            {"property": "oldRevision / newRevision", "type": "str", "usage": sdk.i18n.t("components.complex.codediff.property.revisions")},
            {"property": "hunks", "type": "list[HunkDef]", "usage": sdk.i18n.t("components.complex.codediff.property.hunks")},
            {"property": "showLineNumbers", "type": "bool", "usage": sdk.i18n.t("components.complex.codediff.property.line_numbers")},
        ],
    )
    builder.set_data(
        "/components_complex/codediff_schema",
        [
            {"field": "old_start / new_start", "type": "int", "usage": sdk.i18n.t("components.complex.codediff.schema.starts")},
            {"field": "header", "type": "str", "usage": sdk.i18n.t("components.complex.codediff.schema.header")},
            {"field": "lines", "type": "list[LineDef]", "usage": sdk.i18n.t("components.complex.codediff.schema.lines")},
            {"field": "line.type", "type": "context | add | remove", "usage": sdk.i18n.t("components.complex.codediff.schema.line_type")},
            {"field": "line.text", "type": "str", "usage": sdk.i18n.t("components.complex.codediff.schema.line_text")},
            {"field": "line.old_no / line.new_no", "type": "int", "usage": sdk.i18n.t("components.complex.codediff.schema.line_numbers")},
        ],
    )
    builder.set_data(
        "/components_complex/codediff_updated_model",
        {
            "title": "Runtime guard fix",
            "filePath": "modules/core/logic.py",
            "oldRevision": "a31f9e2",
            "newRevision": "c9bbd51",
            "showLineNumbers": False,
            "hunks": _UPDATED_HUNKS,
        },
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_codediff_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
