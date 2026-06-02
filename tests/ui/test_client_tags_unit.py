from democrai.sdk.templates.full import template as full_template
from clients.qtdesktop.ui.client_tags import ClientTagContext, build_default_client_tag_registry
from clients.qtdesktop.ui.tags import APP_BOTTOM_MAIN_LIST_TAG, APP_MAIN_LIST_TAG


class DummyStore:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=None, scope="auto"):
        return self._values.get(key, default)


class DummyApp:
    def __init__(self, values):
        self.store = DummyStore(values)


def _find_component(components, component_id):
    return next(comp for comp in components if comp["id"] == component_id)


def test_full_template_uses_client_tags_for_sidebar_slots():
    components, dimensions = full_template()

    top_nav = _find_component(components, "top_nav")
    bottom_nav = _find_component(components, "bottom_nav")

    assert dimensions == "full"
    assert top_nav["component"]["ClientTag"]["tag"] == APP_MAIN_LIST_TAG
    assert bottom_nav["component"]["ClientTag"]["tag"] == APP_BOTTOM_MAIN_LIST_TAG


def test_desktop_client_tag_registry_resolves_sidebar_buttons_from_store():
    registry = build_default_client_tag_registry()
    app = DummyApp(
        {
            "/system/modules/top": [
                {
                    "id": "dashboard",
                    "label": "Dashboard",
                    "icon": "ric.function-ai-line",
                    "action": {"name": "nav", "context": {"path": "/dashboard/index"}},
                    "active_condition": {"operator": "OR", "conditions": []},
                }
            ],
            "/system/modules/bottom": [
                {
                    "id": "auth",
                    "label": "Logout",
                    "icon": "ric.logout-box-line",
                    "action": {"name": "logout", "context": {}},
                    "active_condition": {"operator": "OR", "conditions": []},
                }
            ],
            "/core/user/language": "it",
            "/core/supported_languages": [
                {"label": "EN", "value": "en"},
                {"label": "IT", "value": "it"},
            ],
        }
    )

    top_ctx = ClientTagContext(
        surface_id="main",
        component_id="top_nav",
        props={"tag": APP_MAIN_LIST_TAG},
        app_instance=app,
    )
    bottom_ctx = ClientTagContext(
        surface_id="main",
        component_id="bottom_nav",
        props={"tag": APP_BOTTOM_MAIN_LIST_TAG},
        app_instance=app,
    )

    top_components = registry.get(APP_MAIN_LIST_TAG).resolve(top_ctx)
    bottom_components = registry.get(APP_BOTTOM_MAIN_LIST_TAG).resolve(bottom_ctx)

    assert top_components[0]["component"]["List"]["itemTemplate"]["component"]["Button"]["icon"]["iconName"] == "{{icon}}"
    assert top_components[0]["component"]["List"]["itemTemplate"]["component"]["Button"]["action"] == "{{action}}"
    assert top_components[0]["component"]["List"]["dataSource"]["data"][0]["icon"] == "ric.function-ai-line"
    assert top_components[0]["component"]["List"]["dataSource"]["data"][0]["action"]["name"] == "nav"

    assert bottom_components[0]["component"]["List"]["itemTemplate"]["component"]["Button"]["icon"]["iconName"] == "{{icon}}"
    assert bottom_components[0]["component"]["List"]["itemTemplate"]["component"]["Button"]["action"] == "{{action}}"
    assert bottom_components[0]["component"]["List"]["dataSource"]["data"][0]["action"]["name"] == "logout"
    language_component = next(
        comp["component"]["Select"]
        for comp in bottom_components
        if "Select" in comp.get("component", {})
    )
    assert language_component["value"] == "it"
    assert language_component["options"] == [
        {"label": "EN", "value": "en"},
        {"label": "IT", "value": "it"},
    ]
    assert language_component["action"]["name"] == "set_user_language"
