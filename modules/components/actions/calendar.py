from __future__ import annotations

from democrai.sdk.auth import permission_required
from typing import Any

from democrai.sdk.decorators import action


BASE_EVENTS = [
    {
        "_id": "cal_evt_standup",
        "date": "2026-03-05",
        "time": "09:00",
        "title": "Team standup",
        "duration": 30,
        "description": "Daily runtime sync.",
        "color": "#2563eb",
    },
    {
        "_id": "cal_evt_demo",
        "date": "2026-03-10",
        "time": "14:00",
        "title": "Product demo",
        "duration": 60,
        "description": "Component walkthrough.",
        "color": "#16a34a",
    },
    {
        "_id": "cal_evt_board",
        "date": "2026-03-18",
        "time": "11:00",
        "title": "Board review",
        "duration": 120,
        "description": "Quarterly planning session.",
        "color": "#7c3aed",
    },
    {
        "_id": "cal_evt_release",
        "date": "2026-03-26",
        "time": "15:30",
        "title": "Release v2.4",
        "duration": 45,
        "description": "Production release window.",
        "color": "#dc2626",
    },
]

UPDATED_EVENTS = [
    {
        "_id": "cal_evt_gpu",
        "date": "2026-04-02",
        "time": "09:30",
        "title": "GPU capacity review",
        "duration": 60,
        "description": "Check RAM, VRAM, and queue pressure.",
        "color": "#0891b2",
    },
    {
        "_id": "cal_evt_security",
        "date": "2026-04-08",
        "time": "13:00",
        "title": "Security review",
        "duration": 90,
        "description": "Review agent permissions and audit events.",
        "color": "#ca8a04",
    },
    {
        "_id": "cal_evt_ops",
        "date": "2026-04-16",
        "time": "16:00",
        "title": "Operations sync",
        "duration": 45,
        "description": "Follow-up on runtime incidents.",
        "color": "#4f46e5",
    },
]

APPENDED_EVENT = {
    "_id": "cal_evt_added",
    "date": "2026-03-23",
    "time": "10:30",
    "title": "Direct append event",
    "duration": 30,
    "description": "Appended through events.append.",
    "color": "#059669",
}

BASE_BUTTONS = [
    {
        "label": "Add event",
        "variant": "primary",
        "action": {
            "name": "components.calendar_selection_action",
            "context": {"source": "selection_add"},
        },
    },
    {
        "label": "Inspect selection",
        "variant": "default",
        "action": {
            "name": "components.calendar_selection_action",
            "context": {"source": "selection_inspect"},
        },
    },
]

CONFIRM_BUTTONS = [
    {
        "label": "Confirm selection",
        "variant": "primary",
        "action": {
            "name": "components.calendar_selection_action",
            "context": {"source": "confirm_button"},
            "confirm": {
                "text": "@t/components.calendar.confirm.button_prompt",
                "confirm_text": "@t/components.calendar.confirm.accept",
                "cancel_text": "@t/components.calendar.confirm.cancel",
            },
        },
    }
]

DIRECT_CAPABILITIES = [
    "label.set",
    "value.set",
    "current_date.set",
    "view.set",
    "events.set",
    "events.append",
    "selected_dates.set",
    "selected_slots.set",
    "buttons.set",
    "time_from.set",
    "time_to.set",
]


def _surface_id(ctx: dict[str, Any]) -> str:
    return str(ctx.get("_surface_id") or "components_preview").strip() or "components_preview"


def _state_update(sdk, scope: str, values: dict[str, Any]) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages([{"stateUpdate": {"scope": scope, "values": values}}])
    )


def _data_update(sdk, surface_id: str, data: dict[str, Any]) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [sdk.ui.Builder.build_data_model_update_payload(surface_id=surface_id, data=data)]
        )
    )


def _calendar_state(prefix: str, label: str, view: str, date: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        f"{prefix}/value": date,
        f"{prefix}/current_date": date,
        f"{prefix}/view": view,
        f"{prefix}/events": events,
        f"{prefix}/selected_dates": [date] if view == "month" else [],
        f"{prefix}/selected_slots": [{"date": date, "time": "09:00"}] if view == "week" else ["09:30"],
    }


def _calendar_model(label: str, view: str, date: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "value": date,
        "current_date": date,
        "view": view,
        "events": events,
        "selected_dates": [date] if view == "month" else [],
        "selected_slots": [{"date": date, "time": "09:00"}] if view == "week" else ["09:30"],
    }


def _toast_payload(ctx: dict[str, Any]) -> str:
    intent = str(ctx.get("intent") or "button")
    date = str(ctx.get("date") or "")
    time_value = str(ctx.get("time") or "")
    title = str(ctx.get("title") or "")
    source = str(ctx.get("source") or ctx.get("view") or "")
    parts = [f"intent={intent}"]
    if source:
        parts.append(f"source={source}")
    if date:
        parts.append(f"date={date}")
    if time_value:
        parts.append(f"time={time_value}")
    if title:
        parts.append(f"title={title}")
    return "; ".join(parts)


@action("calendar_update")
@permission_required(["components.documentation.view"])
async def calendar_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = _surface_id(ctx)

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            _calendar_state(
                "/components_complex/calendar/page",
                "Page store planning",
                "week",
                "2026-04-02",
                UPDATED_EVENTS,
            ),
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            _calendar_state(
                "/components_complex/calendar/global",
                "Global store planning",
                "day",
                "2026-04-08",
                UPDATED_EVENTS,
            ),
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {
                "components_complex": {
                    "calendar_model": _calendar_model(
                        "Data model planning",
                        "month",
                        "2026-04-16",
                        UPDATED_EVENTS,
                    )
                }
            },
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update("components_complex_calendar_direct", "label", "Direct planning", surface_id=surface_id),
            sdk.effects.ui_property_update("components_complex_calendar_direct", "value", "2026-04-16", surface_id=surface_id),
            sdk.effects.ui_property_update("components_complex_calendar_direct", "current_date", "2026-04-16", surface_id=surface_id),
            sdk.effects.ui_property_update("components_complex_calendar_direct", "view", "week", surface_id=surface_id),
            sdk.effects.ui_property_update("components_complex_calendar_direct", "events", UPDATED_EVENTS, surface_id=surface_id),
            sdk.effects.ui_property_update("components_complex_calendar_direct", "selected_dates", [], surface_id=surface_id),
            sdk.effects.ui_property_update(
                "components_complex_calendar_direct",
                "selected_slots",
                [{"date": "2026-04-16", "time": "16:00"}],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update("components_complex_calendar_direct", "buttons", CONFIRM_BUTTONS, surface_id=surface_id),
            sdk.effects.ui_property_update("components_complex_calendar_direct", "time_from", 7, surface_id=surface_id),
            sdk.effects.ui_property_update("components_complex_calendar_direct", "time_to", 20, surface_id=surface_id),
        )
    return sdk.effects.respond()


@action("calendar_append_direct")
@permission_required(["components.documentation.view"])
async def calendar_append_direct(ctx: dict, session: dict, sdk) -> dict:
    surface_id = _surface_id(ctx)
    return sdk.effects.respond(
        sdk.effects.ui_property_update(
            "components_complex_calendar_direct",
            "events",
            APPENDED_EVENT,
            action="append",
            surface_id=surface_id,
        ),
        sdk.effects.notify(
            "toast",
            {
                "title": "Calendar",
                "text": "Appended one event with events.append.",
                "variant": "success",
                "duration": 2200,
            },
        ),
    )


@action("calendar_interaction")
@permission_required(["components.documentation.view"])
async def calendar_interaction(ctx: dict, session: dict, sdk) -> dict:
    intent = str(ctx.get("intent") or "")
    variant = "info" if intent != "create_event_request" else "success"
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Calendar action",
                "text": _toast_payload(ctx),
                "variant": variant,
                "duration": 2800,
            },
        )
    )


@action("calendar_event_click")
@permission_required(["components.documentation.view"])
async def calendar_event_click(ctx: dict, session: dict, sdk) -> dict:
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Event click",
                "text": _toast_payload(ctx),
                "variant": "info",
                "duration": 2800,
            },
        )
    )


@action("calendar_selection_action")
@permission_required(["components.documentation.view"])
async def calendar_selection_action(ctx: dict, session: dict, sdk) -> dict:
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Selection action",
                "text": _toast_payload(ctx),
                "variant": "success",
                "duration": 2800,
            },
        )
    )
