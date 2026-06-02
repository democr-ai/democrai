from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action


# ---------------------------------------------------------------------------
# Client runtime query demo
# ---------------------------------------------------------------------------

_CLIENT_RUNTIME_STORE_PATH = "/components_flow/client_runtime/store_label"
_CLIENT_RUNTIME_RESULT_PATH = "/components_flow/client_runtime/result"
_CLIENT_RUNTIME_DATA_PATH = "/components_flow/client_runtime/data_label"
_CLIENT_RUNTIME_DIRECT_ID = "components_flow_client_runtime_direct_value"


def _client_runtime_state_result(sdk, text: str) -> dict:
    return {
        "stateUpdate": {
            "scope": "page",
            "values": {_CLIENT_RUNTIME_RESULT_PATH: text},
        }
    }


def _client_runtime_result_payload(sdk, text: str) -> dict:
    return sdk.effects.ui_messages([_client_runtime_state_result(sdk, text)])


def _client_runtime_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _client_runtime_result(title: str, value) -> str:
    return f"### {title}\n\n```json\n{_client_runtime_json(value)}\n```"


def _client_runtime_surface_summary(tree) -> dict:
    if isinstance(tree, dict):
        components = tree.get("components")
        if isinstance(components, dict):
            return {
                "root": tree.get("root") or tree.get("rootId"),
                "components": len(components),
            }
        children = tree.get("children")
        if isinstance(children, list):
            return {
                "id": tree.get("id"),
                "kind": tree.get("kind") or tree.get("type"),
                "children": len(children),
            }
    if isinstance(tree, list):
        return {"roots": len(tree)}
    return {"value": tree}


@action("client_runtime_update")
@permission_required(["components.documentation.view"])
async def client_runtime_update(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "").strip()
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if target == "store":
        return sdk.effects.respond(
            sdk.effects.ui_messages(
                [
                    {
                        "stateUpdate": {
                            "scope": "page",
                            "values": {
                                _CLIENT_RUNTIME_STORE_PATH: sdk.i18n.t(
                                    "components.flow.client_runtime.updated.store"
                                ),
                                _CLIENT_RUNTIME_RESULT_PATH: sdk.i18n.t(
                                    "components.flow.client_runtime.updated.result"
                                ),
                            },
                        }
                    }
                ]
            )
        )

    if target == "data":
        return sdk.effects.respond(
            sdk.effects.ui_messages(
                [
                    sdk.ui.Builder.build_data_model_update_payload(
                        surface_id=surface_id,
                        data={
                            "components_flow": {
                                "client_runtime": {
                                    "data_label": sdk.i18n.t(
                                        "components.flow.client_runtime.updated.data"
                                    )
                                }
                            }
                        },
                    ),
                    _client_runtime_state_result(
                        sdk,
                        sdk.i18n.t("components.flow.client_runtime.updated.result"),
                    ),
                ]
            )
        )

    if target == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                _CLIENT_RUNTIME_DIRECT_ID,
                "text",
                sdk.i18n.t("components.flow.client_runtime.updated.direct"),
                surface_id=surface_id,
            ),
            _client_runtime_result_payload(
                sdk,
                sdk.i18n.t("components.flow.client_runtime.updated.result"),
            ),
        )

    return sdk.effects.respond()


@action("client_runtime_query")
@permission_required(["components.documentation.view"])
async def client_runtime_query(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "").strip()
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    stream_id = str(ctx.get("stream_id") or "").strip() or None

    if target == "store":
        value = await sdk.effects.ask_current_store_value(
            stream_id,
            _CLIENT_RUNTIME_STORE_PATH,
            "page",
        )
        result = _client_runtime_result(
            sdk.i18n.t("components.flow.client_runtime.result.store"),
            value,
        )
        return sdk.effects.respond(_client_runtime_result_payload(sdk, result))

    if target == "data":
        value = await sdk.effects.ask_current_data_value(
            stream_id,
            _CLIENT_RUNTIME_DATA_PATH,
            surface_id=surface_id,
        )
        result = _client_runtime_result(
            sdk.i18n.t("components.flow.client_runtime.result.data"),
            value,
        )
        return sdk.effects.respond(_client_runtime_result_payload(sdk, result))

    if target == "props":
        value = await sdk.effects.ask_current_component_props(
            stream_id,
            _CLIENT_RUNTIME_DIRECT_ID,
            surface_id=surface_id,
        )
        result = _client_runtime_result(
            sdk.i18n.t("components.flow.client_runtime.result.props"),
            value,
        )
        return sdk.effects.respond(_client_runtime_result_payload(sdk, result))

    if target == "tree":
        value = await sdk.effects.ask_current_surface_tree(
            stream_id,
            surface_id=surface_id,
        )
        result = _client_runtime_result(
            sdk.i18n.t("components.flow.client_runtime.result.tree"),
            _client_runtime_surface_summary(value),
        )
        return sdk.effects.respond(_client_runtime_result_payload(sdk, result))

    return sdk.effects.respond()
