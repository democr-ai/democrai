from __future__ import annotations
from typing import Any, Optional
from democrai.sdk.components.base import Component


class Calendar(Component):
    """Advanced calendar component for dates, events, and time-slot selection."""
    type = "Calendar"

    def __init__(
        self,
        id: str,
        value: str = "",
        min_date: str = "",
        max_date: str = "",
        max_width: Optional[int] = None,
        action: Optional[Any] = None,
        params: Optional[dict] = None,
        *,
        # datepicker props (legacy / single-date mode)
        label: str = "",
        date_format: str = "yyyy-MM-dd",
        input_mask: str = "",
        show_input: bool = True,
        # full calendar props
        events: Optional[list] = None,
        view: str = "month",
        current_date: str = "",
        selected_dates: Optional[list] = None,
        selected_slots: Optional[list] = None,
        buttons: Optional[list] = None,
        on_event_click: Optional[Any] = None,
        on_event_click_params: Optional[dict] = None,
        time_from: int = 0,
        time_to: int = 24,
    ):
        super().__init__(id)
        self.mutable_value("value").interactive()
        self.allow(
            "events.set", "events.append", "events.remove", "events.replace",
            "selected_dates.set", "selected_dates.append", "selected_dates.remove",
            "selected_slots.set", "selected_slots.append", "selected_slots.remove",
        )
        self.set_prop("label", {"literalString": label})
        self.set_prop("value", value)
        self.set_prop("min_date", min_date)
        self.set_prop("max_date", max_date)
        self.set_prop("max_width", max_width)
        self.set_prop("date_format", date_format)
        self.set_prop("input_mask", input_mask)
        self.set_prop("show_input", show_input)
        self.set_prop("view", view)
        self.set_prop("current_date", current_date)
        self.set_prop("events", events if events is not None else [])
        self.set_prop("selected_dates", selected_dates if selected_dates is not None else [])
        self.set_prop("selected_slots", selected_slots if selected_slots is not None else [])
        self.set_prop("buttons", self._serialize_buttons(buttons if buttons is not None else []))
        self.set_prop("time_from", max(0, int(time_from)))
        self.set_prop("time_to",   min(24, int(time_to)))
        if on_event_click:
            if isinstance(on_event_click, dict):
                self.set_prop("on_event_click", on_event_click)
            else:
                self.set_prop("on_event_click", {"name": on_event_click, "context": on_event_click_params or {}})
        if action:
            if isinstance(action, dict):
                self.set_prop("action", action)
            else:
                self.set_action(action, params)

    @staticmethod
    def _serialize_buttons(buttons: list) -> list:
        """Normalize custom button definitions into calendar action payloads."""
        out = []
        for btn in buttons:
            if not isinstance(btn, dict):
                continue
            raw_action = btn.get("action")
            params = btn.get("params") or {}
            action = None
            if isinstance(raw_action, dict):
                action = raw_action
            else:
                action_name = raw_action or ""
                action = {"name": action_name, "context": params} if action_name else None
            out.append({
                "label":   btn.get("label") or "",
                "variant": btn.get("variant") or "default",
                "action":  action,
            })
        return out
