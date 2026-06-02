from __future__ import annotations

from typing import Any

from democrai.sdk.auth import is_super_role
from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.decorators import render_hook
from democrai.sdk.system import to_optional_int


def _active_engines(module_sdk) -> list[dict[str, Any]]:
    return (
        module_sdk.models.engine_registry.all(
            filters={"status": "active"},
            sort={"field": "name", "direction": "asc"},
        ).get("rows")
        or []
    )


def _active_models(module_sdk) -> list[dict[str, Any]]:
    return (
        module_sdk.models.model_registry.all(
            filters={"status": "active"},
            sort={"field": "name", "direction": "asc"},
        ).get("rows")
        or []
    )


def _recommendation_card(
    card_id: str,
    *,
    title: str,
    text: str,
    button_label: str,
    path: str,
    icon: str,
):
    title_id = f"{card_id}_title"
    text_id = f"{card_id}_text"
    button_id = f"{card_id}_button"
    body_id = f"{card_id}_body"

    return sdk.ui.Card(
        card_id,
        [
            sdk.ui.Column(
                body_id,
                [
                    sdk.ui.Title(title_id, title, 3),
                    sdk.ui.Text(text_id, text),
                    sdk.ui.Button(
                        button_id,
                        button_label,
                        icon=icon,
                        action="nav",
                        params={"path": path},
                    ),
                ],
            ).set_property("spacing", 10),
        ],
        variant="outlined",
    ).set_property("padding", [18, 18, 18, 18])


@render_hook("auth.profile.recommendations", priority=10)
async def profile_recommendations(params: dict[str, Any], session: dict, module_sdk):
    user = session.get("user") if isinstance(session, dict) else None
    if not isinstance(user, dict):
        return None

    role = str(user.get("role") or "")
    level = to_optional_int(user.get("access_level"))
    if not is_super_role(role, level=level):
        return None

    cards = []
    active_engines = _active_engines(module_sdk)
    active_models = _active_models(module_sdk)

    if not active_engines:
        cards.append(
            _recommendation_card(
                "system_profile_engine_recommendation",
                title=module_sdk.i18n.t("system.profile.recommendation.engine.title"),
                text=module_sdk.i18n.t("system.profile.recommendation.engine.text"),
                button_label=module_sdk.i18n.t(
                    "system.profile.recommendation.engine.action"
                ),
                path="/system/engine/list",
                icon="ric.settings-2-line",
            )
        )

    if not active_models:
        cards.append(
            _recommendation_card(
                "system_profile_model_recommendation",
                title=module_sdk.i18n.t("system.profile.recommendation.model.title"),
                text=module_sdk.i18n.t("system.profile.recommendation.model.text"),
                button_label=module_sdk.i18n.t(
                    "system.profile.recommendation.model.action"
                ),
                path="/system/model/list",
                icon="ric.ai-generate",
            )
        )

    return cards
