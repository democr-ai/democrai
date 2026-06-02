from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_STEPS = [
    {
        "id": "profile",
        "title": "Account",
        "description": "Capture owner profile and billing contact.",
        "content": "Forward navigation stays locked until this step is validated.",
    },
    {
        "id": "workspace",
        "title": "Workspace",
        "description": "Choose workspace settings and default policies.",
        "content": "Backward navigation remains available without another validation.",
    },
    {
        "id": "access",
        "title": "Access",
        "description": "Invite users and assign initial roles.",
        "content": "Direct forward jumps require every previous step to be validated.",
    },
    {
        "id": "review",
        "title": "Review",
        "description": "Confirm the configuration before activation.",
        "content": "The final step is reachable only after the earlier gates are complete.",
    },
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/wizard"), components=True)

    builder.set_data(
        "/components_complex/wizard_bindings",
        [
            {"binding": "Literal", "yaml": "steps:\n  - id: profile\n    title: Account", "source": "YAML or Python constructor"},
            {"binding": "Initial state", "yaml": "active_step_id: profile\nvalidated_steps: []", "source": "YAML or Python constructor"},
            {"binding": "Runtime state", "yaml": "capabilities: [steps.set, active_step_id.set, validated_steps.set]", "source": "sdk.effects.ui_property_update(...)"},
            {"binding": "Current state query", "yaml": "params: {target_wizard: components_complex_wizard_live}", "source": "sdk.effects.ask_current_component_props(...)"},
        ],
    )
    builder.set_data(
        "/components_complex/wizard_properties",
        [
            {"property": "steps", "type": "list[Step]", "usage": sdk.i18n.t("components.complex.wizard.property.steps")},
            {"property": "active_step_id", "type": "str", "usage": sdk.i18n.t("components.complex.wizard.property.active_step_id")},
            {"property": "validated_steps", "type": "list[str]", "usage": sdk.i18n.t("components.complex.wizard.property.validated_steps")},
            {"property": "action", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.wizard.property.action")},
            {"property": "params", "type": "dict", "usage": sdk.i18n.t("components.complex.wizard.property.params")},
            {"property": "allow_step_click / show_controls", "type": "bool", "usage": sdk.i18n.t("components.complex.wizard.property.flags")},
            {"property": "prev_label / next_label", "type": "str", "usage": sdk.i18n.t("components.complex.wizard.property.labels")},
        ],
    )
    builder.set_data(
        "/components_complex/wizard_step_schema",
        [
            {"field": "id", "type": "str", "usage": sdk.i18n.t("components.complex.wizard.schema.id")},
            {"field": "title", "type": "str", "usage": sdk.i18n.t("components.complex.wizard.schema.title")},
            {"field": "description", "type": "str", "usage": sdk.i18n.t("components.complex.wizard.schema.description")},
            {"field": "content", "type": "str", "usage": sdk.i18n.t("components.complex.wizard.schema.content")},
            {"field": "status", "type": "str", "usage": sdk.i18n.t("components.complex.wizard.schema.status")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_wizard_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
