from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout
from ...actions.calendar import BASE_BUTTONS, BASE_EVENTS, DIRECT_CAPABILITIES


def _seed_store(builder, scope: str, prefix: str) -> None:
    builder.set_store(f"{prefix}/value", "2026-03-01", scope=scope)
    builder.set_store(f"{prefix}/current_date", "2026-03-01", scope=scope)
    builder.set_store(f"{prefix}/view", "month", scope=scope)
    builder.set_store(f"{prefix}/events", BASE_EVENTS, scope=scope)
    builder.set_store(f"{prefix}/selected_dates", ["2026-03-18"], scope=scope)
    builder.set_store(f"{prefix}/selected_slots", [], scope=scope)


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/calendar"), components=True)

    _seed_store(builder, "page", "/components_complex/calendar/page")
    _seed_store(builder, "global", "/components_complex/calendar/global")
    builder.set_data(
        "/components_complex/calendar_model",
        {
            "value": "2026-03-01",
            "current_date": "2026-03-01",
            "view": "month",
            "events": BASE_EVENTS,
            "selected_dates": ["2026-03-18"],
            "selected_slots": [],
        },
    )
    builder.set_data(
        "/components_complex/calendar_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "events:\n  - date: \"2026-03-05\"\n    title: Team standup",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_complex/calendar/page/events}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_complex/calendar/global/events}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_complex/calendar_model/events",
                "source": "builder.set_data(...)",
            },
            {
                "binding": "Direct property",
                "yaml": "capabilities: [label.set, buttons.set, time_from.set, time_to.set]",
                "source": "sdk.effects.ui_property_update(...)",
            },
        ],
    )
    builder.set_data(
        "/components_complex/calendar_properties",
        [
            {"property": "label / value", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.property.label_value")},
            {"property": "view", "type": "month | week | day", "usage": sdk.i18n.t("components.complex.calendar.property.view")},
            {"property": "current_date", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.property.current_date")},
            {"property": "events", "type": "list[Event]", "usage": sdk.i18n.t("components.complex.calendar.property.events")},
            {"property": "selected_dates", "type": "list[str]", "usage": sdk.i18n.t("components.complex.calendar.property.selected_dates")},
            {"property": "selected_slots", "type": "list[dict] | list[str]", "usage": sdk.i18n.t("components.complex.calendar.property.selected_slots")},
            {"property": "buttons", "type": "list[ActionButton]", "usage": sdk.i18n.t("components.complex.calendar.property.buttons")},
            {"property": "action", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.calendar.property.action")},
            {"property": "on_event_click", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.calendar.property.on_event_click")},
            {"property": "time_from / time_to", "type": "int", "usage": sdk.i18n.t("components.complex.calendar.property.time_range")},
        ],
    )
    builder.set_data(
        "/components_complex/calendar_event_schema",
        [
            {"field": "_id", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.event.id")},
            {"field": "date", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.event.date")},
            {"field": "start", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.event.start")},
            {"field": "time", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.event.time")},
            {"field": "title", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.event.title")},
            {"field": "duration", "type": "int", "usage": sdk.i18n.t("components.complex.calendar.event.duration")},
            {"field": "description", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.event.description")},
            {"field": "color", "type": "str", "usage": sdk.i18n.t("components.complex.calendar.event.color")},
        ],
    )
    builder.set_data(
        "/components_complex/calendar_intents",
        [
            {"intent": "navigate", "clients": "Desktop, Web", "payload": "view, direction, date"},
            {"intent": "view_change", "clients": "Desktop, Web", "payload": "view, optional date"},
            {"intent": "day_click", "clients": "Desktop, Web", "payload": "view, date"},
            {"intent": "slot_click", "clients": "Desktop, Web", "payload": "view, date, time"},
            {"intent": "create_event_request", "clients": "Desktop", "payload": "view, date, time"},
            {"intent": "on_event_click", "clients": "Desktop, Web", "payload": "event, date, time, title"},
            {"intent": "buttons[].action", "clients": "Desktop, Web", "payload": "button context + current selection"},
        ],
    )
    builder.set_data(
        "/components_complex/calendar_capabilities",
        [{"capability": item, "usage": sdk.i18n.t("components.complex.calendar.capability.mutable")} for item in DIRECT_CAPABILITIES],
    )
    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_calendar_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
