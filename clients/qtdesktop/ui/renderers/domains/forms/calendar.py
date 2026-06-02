from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import QDate, QDateTime, QSize, QTime, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...icon import get_icon
from ....theme.tokens import calendar_theme, themed_status_color

from ...base import BaseRenderer, confirm_action, emit_action_spec, publish_bound_value
from .common import _field_shell, _literal, _parse_qdate


# ─── colours (match web renderer exactly) ─────────────────────────────────────

_C = calendar_theme()

_MONTH_LONG = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December",
]
_MONTH_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
_DAY_NAMES   = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]


# ─── helpers ──────────────────────────────────────────────────────────────────

def _fmt_date(iso: str) -> str:
    try:
        p = iso.split("-")
        return f"{_MONTH_SHORT[int(p[1])-1]} {int(p[2])}"
    except Exception:
        return iso


def _btn_style(variant: str, small: bool = False) -> str:
    pad = "3px 10px" if small else "5px 14px"
    fs  = 12 if small else 13
    if variant == "primary":
        return (f"QPushButton {{ background: {_C['blue']}; border: 1px solid {_C['blue']}; "
                f"color:{_C['title']}; padding:{pad}; border-radius:6px; font-size:{fs}px; font-weight:500; }}"
                f"QPushButton:hover {{ background:{_C['sel_border']}; }}")
    if variant == "default":
        return (f"QPushButton {{ background:{_C['abar_bg']}; border:1px solid {_C['abar_border']}; color:{_C['title']}; "
                f"padding:{pad}; border-radius:6px; font-size:{fs}px; font-weight:500; }}"
                f"QPushButton:hover {{ background:{_C['border']}; }}")
    # ghost
    return (f"QPushButton {{ background:transparent; border:none; color:{_C['nav']}; "
            f"padding:{pad}; border-radius:6px; font-size:{fs}px; font-weight:500; }}"
            f"QPushButton:hover {{ color:{_C['title']}; }}")


class _CellFrame(QFrame):
    """Clickable QFrame used for day/slot cells."""
    def __init__(self, on_click=None, on_right_click=None, parent=None):
        super().__init__(parent)
        self._on_click       = on_click
        self._on_right_click = on_right_click
        if on_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton and self._on_right_click:
            self._on_right_click(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)


# ─── day grid (absolute-positioned, supports multi-event + spanning) ──────────

class _DayGrid(QWidget):
    """
    Day view grid using absolute child positioning.

    Layout:
    • Left strip (TIME_W px): per-slot time labels (shown only on :00 slots)
    • Right area: slot background cells (clickable for selection, z=0) +
      event blocks absolutely positioned on top (z=1, higher z via later creation)

    resizeEvent repositions every child to keep the layout consistent on resize.
    """
    SLOT_H = 44   # px per 30-min slot
    TIME_W = 56   # px for time label column

    def __init__(
        self,
        slots: list[str],
        ev_layout: list[tuple],   # [(ev, start_idx, span, col)]
        day_slots: set[str],
        on_slot_click,
        on_ev_click,
        has_ev_handler: bool,
    ):
        super().__init__()
        self._slots      = slots
        self._ev_layout  = ev_layout
        self._day_slots  = day_slots
        self._n_ev_cols  = max((col + 1 for _, _, _, col in ev_layout), default=1)

        total_h = len(slots) * self.SLOT_H
        self.setMinimumHeight(total_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setStyleSheet(f"background:{_C['bg']};")

        # ── time labels (clickable — selects the slot)
        self._time_lbls: list[QLabel] = []
        for slot in slots:
            text = slot if slot.endswith(":00") else ""
            lbl  = QLabel(text, self)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            lbl.setStyleSheet(
                f"font-size:12px; color:{_C['time']}; padding:4px 8px 0 0; "
                f"background:transparent; border:none;"
            )
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda _e, t=slot: on_slot_click(t)  # type: ignore[assignment]
            self._time_lbls.append(lbl)

        # ── slot background cells (z=0 — created before events)
        self._slot_cells: list[_CellFrame] = []
        for slot in slots:
            is_sel = slot in day_slots
            row_bg = _C["slot_sel"] if is_sel else _C["bg"]
            cell   = _CellFrame(on_click=lambda t=slot: on_slot_click(t), parent=self)
            cell.setStyleSheet(
                f"QFrame {{ background:{row_bg}; border-top:1px solid {_C['border']}; }}"
                f"QLabel {{ background:transparent; border:none; }}"
            )
            self._slot_cells.append(cell)

        # ── event blocks (z=1 — created after slot cells → painted on top)
        self._ev_widgets: list[tuple] = []   # (widget, si, span, col)
        for ev, si, span, col in ev_layout:
            color  = ev.get("color", themed_status_color("planned"))
            is_sel = slots[si] in day_slots if si < len(slots) else False
            bg_a   = "55" if is_sel else "22"

            content = _CellFrame(
                on_click=(lambda e=ev: on_ev_click(e)) if has_ev_handler else None,
                parent=self,
            )
            content.setStyleSheet(
                f"QFrame {{ background:{color}{bg_a}; border-left:3px solid {color}; border-radius:4px; }}"
                f"QLabel {{ background:transparent; border:none; }}"
            )
            if has_ev_handler:
                content.setCursor(Qt.CursorShape.PointingHandCursor)

            cl = QVBoxLayout(content)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(1)

            t_lbl = QLabel(ev.get("time", ""))
            t_lbl.setStyleSheet(
                f"font-size:10px; color:{color}; font-weight:600; background:transparent;"
            )
            cl.addWidget(t_lbl)

            ttl = QLabel(ev.get("title", ""))
            ttl.setStyleSheet(
                f"font-size:13px; color:{color}; font-weight:600; background:transparent;"
            )
            cl.addWidget(ttl)

            if ev.get("description"):
                desc = QLabel(str(ev["description"]))
                desc.setStyleSheet(
                    f"font-size:11px; color:{color}99; background:transparent;"
                )
                cl.addWidget(desc)

            cl.addStretch()
            self._ev_widgets.append((content, si, span, col))

    # ── Qt overrides ───────────────────────────────────────────────────────

    def sizeHint(self):
        return QSize(400, len(self._slots) * self.SLOT_H)

    def minimumSizeHint(self):
        return QSize(200, len(self._slots) * self.SLOT_H)

    def resizeEvent(self, event):
        self._relayout()
        super().resizeEvent(event)

    def _relayout(self) -> None:
        W  = self.width()
        ea = max(W - self.TIME_W, 1)   # event-area width
        SH = self.SLOT_H
        nc = self._n_ev_cols

        for i, lbl in enumerate(self._time_lbls):
            lbl.setGeometry(0, i * SH, self.TIME_W, SH)

        for i, cell in enumerate(self._slot_cells):
            cell.setGeometry(self.TIME_W, i * SH, ea, SH)

        col_w = ea // nc if nc > 0 else ea
        for (widget, si, span, col) in self._ev_widgets:
            x = self.TIME_W + col * col_w + 2
            y = si * SH + 2
            w = max(col_w - 4, 10)
            h = max(span * SH - 4, 10)
            widget.setGeometry(x, y, w, h)


# ─── main widget ──────────────────────────────────────────────────────────────

class _AdvancedCalendarWidget(QFrame):

    def __init__(self, props: Dict[str, Any], *, surface_id: str, app_instance: Any, comp_id: str):
        super().__init__()
        self._props        = dict(props)
        self._surface_id   = surface_id
        self._app_instance = app_instance
        self._comp_id      = comp_id

        self._current_date = (
            _parse_qdate(self._props.get("current_date"))
            or _parse_qdate(self._props.get("value"))
            or QDate.currentDate()
        )
        self._view = str(self._props.get("view") or "month").strip().lower()
        if self._view not in {"day", "week", "month"}:
            self._view = "month"

        self.setStyleSheet(f"background:{_C['bg']};")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self._build_tab_bar()

        # Content container — no scroll, expands to fit content naturally
        self._content_wrap = QWidget()
        self._content_wrap.setStyleSheet(f"background:{_C['bg']};")
        self._content_layout = QVBoxLayout(self._content_wrap)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._root.addWidget(self._content_wrap)

        self._refresh()

    # ── props ──────────────────────────────────────────────────────────────

    def update_prop(self, name: str, value: Any) -> None:
        self._props[name] = value
        if name in ("value", "current_date"):
            qd = _parse_qdate(value)
            if qd and qd.isValid():
                self._current_date = qd
        if name == "view":
            nxt = str(value or "").strip().lower()
            if nxt in {"day", "week", "month"}:
                self._view = nxt
        self._refresh()

    def _events(self) -> list[dict]:
        evs = self._props.get("events")
        return evs if isinstance(evs, list) else []

    def _action(self) -> dict:
        a = self._props.get("action")
        return a if isinstance(a, dict) else {}

    def _selected_dates(self) -> set[str]:
        raw = self._props.get("selected_dates")
        return {str(s) for s in raw if isinstance(s, str)} if isinstance(raw, list) else set()

    def _selected_week_slots(self) -> list[dict]:
        raw = self._props.get("selected_slots")
        return [s for s in raw if isinstance(s, dict) and s.get("date")] if isinstance(raw, list) else []

    def _selected_day_slots(self) -> set[str]:
        raw = self._props.get("selected_slots")
        return {s for s in raw if isinstance(s, str)} if isinstance(raw, list) else set()

    def _week_slots(self) -> list[str]:
        h0 = max(0,  int(self._props.get("time_from") or 0))
        h1 = min(24, int(self._props.get("time_to")   or 24))
        return [f"{h:02d}:00" for h in range(h0, h1)]

    def _day_slots(self) -> list[str]:
        h0 = max(0,  int(self._props.get("time_from") or 0))
        h1 = min(24, int(self._props.get("time_to")   or 24))
        return [f"{h:02d}:{m:02d}" for h in range(h0, h1) for m in (0, 30)]

    def _buttons(self) -> list[dict]:
        raw = self._props.get("buttons")
        return [b for b in raw if isinstance(b, dict)] if isinstance(raw, list) else []

    def _make_custom_btn(self, btn: dict, sel_context: dict) -> QPushButton:
        action_spec = btn.get("action") or {}
        action_name = action_spec.get("name", "") if isinstance(action_spec, dict) else ""
        label   = str(btn.get("label") or "")
        variant = str(btn.get("variant") or "default")

        b = QPushButton(label)
        b.setStyleSheet(_btn_style(variant, small=True))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if action_name:
            b.clicked.connect(lambda _checked=False, a=action_spec, c=sel_context: emit_action_spec(
                self._app_instance, a, c, self._surface_id, self._comp_id,
            ))
        return b

    # ── action emission ────────────────────────────────────────────────────

    def _emit(self, payload: dict) -> bool:
        a = self._action()
        if not a:
            return True
        confirm = a.get("confirm") if isinstance(a, dict) else None
        if a and not confirm_action(self._app_instance, confirm):
            return False
        action_spec = dict(a)
        action_spec.pop("confirm", None)
        emit_action_spec(
            self._app_instance,
            action_spec,
            payload,
            self._surface_id,
            self._comp_id,
        )
        return True

    # ── events by day ──────────────────────────────────────────────────────

    def _events_for_day(self, day: QDate) -> list[dict]:
        out = []
        for ev in self._events():
            if not isinstance(ev, dict):
                continue
            date_str = str(ev.get("date") or "")
            start_str = str(ev.get("start") or "")
            if date_str:
                d = QDate.fromString(date_str, "yyyy-MM-dd")
            elif start_str:
                d = QDateTime.fromString(start_str, Qt.DateFormat.ISODate).date()
            else:
                continue
            if d.isValid() and d == day:
                out.append(ev)
        return out

    def _hour_for_event(self, ev: dict) -> int:
        t = str(ev.get("time") or "")
        if t:
            try:
                return int(t.split(":")[0])
            except ValueError:
                pass
        start = str(ev.get("start") or "")
        if start:
            dt = QDateTime.fromString(start, Qt.DateFormat.ISODate)
            if dt.isValid():
                return dt.time().hour()
        return -1

    # ── tab bar ────────────────────────────────────────────────────────────

    def _build_tab_bar(self) -> None:
        frame = QFrame()
        frame.setStyleSheet(f"background:{_C['bg']}; border-bottom:1px solid {_C['border']};")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._tab_btns: dict[str, QPushButton] = {}
        for key, label in [("month", "Month"), ("week", "Week"), ("day", "Day")]:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, v=key: self._set_view(v))
            self._tab_btns[key] = btn
            layout.addWidget(btn)
        layout.addStretch()
        self._root.addWidget(frame)

    def _update_tab_styles(self) -> None:
        for key, btn in self._tab_btns.items():
            active = self._view == key
            bc = _C["blue"] if active else "transparent"
            fg = _C["blue"] if active else _C["hdr"]
            btn.setStyleSheet(
                f"QPushButton {{ padding:8px 18px; font-size:13px; font-weight:600; "
                f"border:none; border-bottom:2px solid {bc}; border-radius:0; "
                f"background:transparent; color:{fg}; }}"
                f"QPushButton:hover {{ color:{_C['title']}; }}"
            )

    # ── nav row ────────────────────────────────────────────────────────────

    def _build_nav_row(self, title: str, subtitle: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{_C['bg']};")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        def _nav_btn(icon_name: str) -> QPushButton:
            b = QPushButton()
            b.setFixedSize(32, 32)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIcon(get_icon(icon_name, _C["nav"], 18))
            b.setIconSize(QSize(18, 18))
            b.setStyleSheet(
                f"QPushButton {{ background:none; border:none; border-radius:4px; }}"
                f"QPushButton:hover {{ background:{_C['border']}; }}"
            )
            return b

        prev = _nav_btn("ric.arrow-left-s-line")
        nxt  = _nav_btn("ric.arrow-right-s-line")
        prev.clicked.connect(lambda: self._navigate(-1))
        nxt.clicked.connect(lambda: self._navigate(1))

        title_col = QWidget()
        title_col.setStyleSheet(f"background:{_C['bg']};")
        tl = QVBoxLayout(title_col)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)

        t = QLabel(title)
        t.setStyleSheet(f"font-size:16px; font-weight:700; color:{_C['title']}; background:transparent;")
        tl.addWidget(t)

        s = QLabel(subtitle)
        s.setStyleSheet(f"font-size:12px; color:{_C['sub']}; background:transparent;")
        tl.addWidget(s)

        layout.addWidget(prev)
        layout.addWidget(title_col, 1)
        layout.addWidget(nxt)
        return w

    # ── action bars ────────────────────────────────────────────────────────

    def _abar_frame(self) -> tuple[QFrame, QHBoxLayout]:
        f = QFrame()
        f.setStyleSheet(
            f"QFrame {{ background:{_C['abar_bg']}; border:1px solid {_C['abar_border']}; border-radius:8px; }}"
        )
        l = QHBoxLayout(f)
        l.setContentsMargins(14, 8, 14, 8)
        l.setSpacing(10)
        return f, l

    def _abar_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size:13px; color:{_C['nav']}; background:transparent; border:none;")
        return lbl

    def _action_bar_empty(self) -> QFrame:
        """Placeholder bar shown when nothing is selected — keeps layout stable."""
        f, l = self._abar_frame()
        lbl = QLabel("No selection")
        lbl.setStyleSheet(f"font-size:12px; color:{_C['hdr']}; background:transparent; border:none;")
        l.addWidget(lbl)
        l.addStretch()
        return f

    def _action_bar_month(self, sel_day: str) -> QFrame:
        f, l = self._abar_frame()
        l.addWidget(self._abar_label(f"Selected: {_fmt_date(sel_day)}"))

        vd = QPushButton("View day")
        vd.setStyleSheet(_btn_style("default", small=True))
        vd.clicked.connect(lambda: self._switch_to_day(sel_day))
        l.addWidget(vd)

        for btn in self._buttons():
            l.addWidget(self._make_custom_btn(btn, {"date": sel_day}))

        clr = QPushButton("Clear selection")
        clr.setStyleSheet(_btn_style("ghost", small=True))
        clr.clicked.connect(lambda: self._clear_selection("month"))
        l.addWidget(clr)

        l.addStretch()
        return f

    def _action_bar_slots(self, view: str, slots) -> QFrame:
        f, l = self._abar_frame()
        count = len(slots)
        sfx   = "s" if count > 1 else ""
        if view == "week":
            date  = slots[0].get("date", "") if slots else ""
            times = ", ".join(s.get("time", "") for s in slots)
            desc  = f"{count} slot{sfx} on {_fmt_date(date)} · {times}"
            sel_context = {
                "date":  date,
                "time":  slots[0].get("time", "") if slots else "",
                "slots": slots,
            }
        else:
            date = self._current_date.toString("yyyy-MM-dd")
            desc = f"{count} slot{sfx} selected · {', '.join(slots)}"
            sel_context = {
                "date":  date,
                "time":  list(slots)[0] if slots else "",
                "slots": list(slots),
            }

        l.addWidget(self._abar_label(desc))

        for btn in self._buttons():
            l.addWidget(self._make_custom_btn(btn, sel_context))

        clr = QPushButton("Clear selection")
        clr.setStyleSheet(_btn_style("ghost", small=True))
        clr.clicked.connect(lambda v=view: self._clear_selection(v))
        l.addWidget(clr)

        l.addStretch()
        return f

    # ── navigation / view switch ───────────────────────────────────────────

    def _navigate(self, delta: int) -> None:
        next_date = self._current_date.addDays(0)
        if self._view == "day":
            next_date = next_date.addDays(delta)
        elif self._view == "week":
            next_date = next_date.addDays(7 * delta)
        else:
            next_date = next_date.addMonths(delta)
        if not self._emit({"intent": "navigate", "view": self._view, "direction": delta,
                           "date": next_date.toString("yyyy-MM-dd")}):
            return
        self._current_date = next_date
        self._refresh()

    def _set_view(self, view: str) -> None:
        if not self._emit({"intent": "view_change", "view": view}):
            return
        self._view = view
        self._refresh()

    def _emit_event_click(self, ev: dict) -> None:
        a = self._props.get("on_event_click")
        if not isinstance(a, dict) or not a.get("name"):
            return
        emit_action_spec(
            self._app_instance,
            a,
            {"event": ev, "date": ev.get("date", ""), "time": ev.get("time", ""),
             "title": ev.get("title", "")},
            self._surface_id,
            self._comp_id,
        )

    def _clear_selection(self, view: str) -> None:
        if view == "month":
            self._props["selected_dates"] = []
        else:
            self._props["selected_slots"] = []
        self._refresh()

    def _switch_to_day(self, date_str: str) -> None:
        if not self._emit({"intent": "view_change", "view": "day", "date": date_str}):
            return
        qd = _parse_qdate(date_str)
        if qd and qd.isValid():
            self._current_date = qd
        self._view = "day"
        self._refresh()

    # ── refresh (rebuilds entire visible content) ──────────────────────────

    def _refresh(self) -> None:
        self._update_tab_styles()

        # Clear existing content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        vl = self._content_layout
        vl.setContentsMargins(0, 8, 0, 0)
        vl.setSpacing(10)

        if self._view == "month":
            vl.addWidget(self._build_nav_row(
                f"{_MONTH_LONG[self._current_date.month()-1]} {self._current_date.year()}",
                "Click a day to select it"))
            sel = self._selected_dates()
            vl.addWidget(self._action_bar_month(next(iter(sel))) if sel else self._action_bar_empty())
            vl.addWidget(self._build_month())

        elif self._view == "week":
            monday = self._current_date.addDays(1 - self._current_date.dayOfWeek())
            sunday = monday.addDays(6)
            if monday.month() == sunday.month():
                wl = f"Week · {monday.toString('MMM d')} – {sunday.day()}, {sunday.year()}"
            else:
                wl = f"Week · {monday.toString('MMM d')} – {sunday.toString('MMM d')}, {sunday.year()}"
            vl.addWidget(self._build_nav_row(wl, "Click a slot · same-day multi-select"))
            slots = self._selected_week_slots()
            vl.addWidget(self._action_bar_slots("week", slots) if slots else self._action_bar_empty())
            vl.addWidget(self._build_week())

        else:  # day
            d = self._current_date
            day_lbl = f"{_DAY_NAMES[d.dayOfWeek()-1]}, {_MONTH_LONG[d.month()-1]} {d.day()}, {d.year()}"
            vl.addWidget(self._build_nav_row(day_lbl, "Click a slot · multi-select"))
            day_slots = self._selected_day_slots()
            vl.addWidget(self._action_bar_slots("day", sorted(day_slots)) if day_slots else self._action_bar_empty())
            vl.addWidget(self._build_day())

        vl.addStretch()

    # ── month view ─────────────────────────────────────────────────────────

    def _build_month(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{_C['bg']};")
        grid = QGridLayout(w)
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)

        # weekday headers
        for ci, dn in enumerate(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]):
            lbl = QLabel(dn)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"font-size:11px; font-weight:700; text-transform:uppercase; "
                f"color:{_C['hdr']}; padding:8px 4px; background:transparent;"
            )
            grid.addWidget(lbl, 0, ci)

        # day cells
        year  = self._current_date.year()
        month = self._current_date.month()
        first = QDate(year, month, 1)
        start = first.addDays(-(first.dayOfWeek() - 1))
        sel   = self._selected_dates()
        today = QDate.currentDate()

        for ri in range(6):
            for ci in range(7):
                day = start.addDays(ri * 7 + ci)
                ds  = day.toString("yyyy-MM-dd")
                evs = self._events_for_day(day)
                in_month = day.month() == month
                is_today = day == today
                is_sel   = ds in sel

                if is_sel:
                    cell_bg, cell_border = _C["sel_bg"], f"2px solid {_C['sel_border']}"
                elif not in_month:
                    cell_bg, cell_border = _C["outside"], f"1px solid {_C['border']}"
                else:
                    cell_bg, cell_border = _C["bg"], f"1px solid {_C['border']}"

                cell = _CellFrame(
                    on_click=lambda d=ds: self._on_day_click(d),
                    on_right_click=lambda pos, d=ds: self._on_day_right_click(d, pos),
                )
                # Use QFrame selector — _CellFrame is a QFrame subclass; plain property
                # values (no selector) would cascade to children, so we scope to QFrame.
                cell.setStyleSheet(
                    f"QFrame {{ background:{cell_bg}; border:{cell_border}; border-radius:4px; }}"
                    f"QLabel {{ background:transparent; border:none; }}"
                    f"QPushButton {{ border:none; }}"
                )
                cell.setMinimumHeight(80)

                cl = QVBoxLayout(cell)
                cl.setContentsMargins(4, 4, 4, 4)
                cl.setSpacing(1)

                # day number — use QLabel (no button chrome) so the text is always crisp
                num_fg = (
                    _C["title"] if is_sel   else
                    _C["blue"]  if is_today else
                    _C["title"] if in_month else
                    _C["sub"]
                )
                num_weight = "800" if is_today else "600" if is_sel else "400"
                num_border = f"border:1px solid {_C['blue']};" if is_today else ""

                day_lbl = QLabel(str(day.day()))
                day_lbl.setFixedSize(24, 24)
                day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                day_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
                day_lbl.setStyleSheet(
                    f"font-size:12px; font-weight:{num_weight}; color:{num_fg}; "
                    f"border-radius:12px; background:{_C['blue'] if is_sel else 'transparent'}; "
                    f"{num_border}"
                )
                # forward click to cell handler
                day_lbl.mousePressEvent = lambda _e, d=ds: self._on_day_click(d)  # type: ignore[assignment]
                cl.addWidget(day_lbl)

                # event pills — clickable if on_event_click is set
                for ev in evs[:2]:
                    color = ev.get("color") or themed_status_color("planned")
                    t     = ev.get("time","")
                    title = ev.get("title","")
                    has_handler = bool(self._props.get("on_event_click"))
                    pill_frame = _CellFrame(
                        on_click=(lambda e=ev: self._emit_event_click(e)) if has_handler else None,
                    )
                    pill_frame.setStyleSheet("background:transparent; border:none;")
                    if has_handler:
                        pill_frame.setCursor(Qt.CursorShape.PointingHandCursor)
                    pfl = QHBoxLayout(pill_frame)
                    pfl.setContentsMargins(2, 1, 2, 1)
                    pfl.setSpacing(0)
                    pill = QLabel(f"● {t+' ' if t else ''}{title}")
                    pill.setStyleSheet(
                        f"font-size:10px; color:{color}; background:transparent; "
                        f"padding:1px 3px;"
                    )
                    pill.setWordWrap(False)
                    pfl.addWidget(pill)
                    cl.addWidget(pill_frame)

                if len(evs) > 2:
                    more = QLabel(f"+{len(evs)-2} more")
                    more.setStyleSheet(f"font-size:10px; color:{_C['time']}; background:transparent; padding:1px 3px;")
                    cl.addWidget(more)

                cl.addStretch()
                grid.addWidget(cell, ri + 1, ci)

        for ci in range(7):
            grid.setColumnStretch(ci, 1)
        return w

    def _on_day_click(self, ds: str) -> None:
        if not self._emit({"intent": "day_click", "view": "month", "date": ds}):
            return
        self._props["selected_dates"] = [ds]
        self._refresh()

    def _on_day_right_click(self, ds: str, pos) -> None:
        menu = QMenu(self)
        act = menu.addAction("Add event here")
        sel = menu.exec(self.mapToGlobal(pos))
        if sel == act:
            self._emit({"intent": "create_event_request", "view": "month", "date": ds, "time": "09:00"})

    # ── week view ──────────────────────────────────────────────────────────

    def _build_week(self) -> QWidget:
        monday = self._current_date.addDays(1 - self._current_date.dayOfWeek())
        days   = [monday.addDays(i) for i in range(7)]
        today  = QDate.currentDate()
        sel    = {(s["date"], s["time"][:2]) for s in self._selected_week_slots() if s.get("time")}

        w = QWidget()
        w.setStyleSheet(f"background:{_C['bg']};")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # column headers
        hdr = QWidget()
        hdr.setStyleSheet(f"background:{_C['bg']}; border-bottom:1px solid {_C['border']};")
        hl  = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        corner = QLabel("")
        corner.setFixedWidth(56)
        corner.setStyleSheet("background:transparent;")
        hl.addWidget(corner)

        for day in days:
            ds  = day.toString("yyyy-MM-dd")
            fg  = _C["blue"] if day == today else _C["nav"]
            lbl = QLabel(f"{day.toString('ddd')}\n{day.day()}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"font-size:11px; font-weight:700; color:{fg}; "
                f"padding:6px 4px; background:transparent;"
            )
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda _e, d=ds: self._switch_to_day(d)  # type: ignore[assignment]
            hl.addWidget(lbl, 1)

        vl.addWidget(hdr)

        # slot rows
        for slot in self._week_slots():
            row_w = QWidget()
            row_w.setStyleSheet(f"background:{_C['bg']}; border-top:1px solid {_C['border']};")
            rl    = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)

            time_lbl = QLabel(slot)
            time_lbl.setFixedWidth(56)
            time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            time_lbl.setStyleSheet(
                f"font-size:11px; color:{_C['time']}; padding:4px 8px 4px 0; "
                f"background:transparent;"
            )
            time_lbl.setFixedHeight(32)
            rl.addWidget(time_lbl)

            for day in days:
                ds    = day.toString("yyyy-MM-dd")
                evs   = [e for e in self._events_for_day(day) if self._hour_for_event(e) == int(slot[:2])]
                is_sel = (ds, slot[:2]) in sel
                color = evs[0].get("color", themed_status_color("planned")) if evs else themed_status_color("planned")

                if is_sel:
                    bg     = _C["slot_sel"]
                    border = f"1px solid {_C['blue']}44"
                elif evs:
                    bg     = f"{color}22"
                    border = f"1px solid {_C['border']}"
                else:
                    bg     = "transparent"
                    border = f"1px solid {_C['border']}"

                cell = _CellFrame(on_click=lambda d=ds, t=slot: self._on_week_slot_click(d, t))
                cell.setStyleSheet(
                    f"QFrame {{ background:{bg}; border-left:{border}; }}"
                    f"QLabel {{ background:transparent; border:none; }}"
                )
                cell.setFixedHeight(32)
                cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

                cl = QVBoxLayout(cell)
                cl.setContentsMargins(2, 1, 2, 1)
                cl.setSpacing(0)

                if evs:
                    has_handler = bool(self._props.get("on_event_click"))
                    ev0 = evs[0]
                    ev0_color = ev0.get("color", themed_status_color("planned"))
                    pill_frame = _CellFrame(
                        on_click=(lambda e=ev0: self._emit_event_click(e)) if has_handler else None,
                    )
                    pill_frame.setStyleSheet("background:transparent; border:none;")
                    if has_handler:
                        pill_frame.setCursor(Qt.CursorShape.PointingHandCursor)
                    pfl = QHBoxLayout(pill_frame)
                    pfl.setContentsMargins(2, 1, 2, 1)
                    pfl.setSpacing(0)
                    extra = f" +{len(evs)-1}" if len(evs) > 1 else ""
                    pill = QLabel(f"● {ev0.get('title','')}{extra}")
                    pill.setStyleSheet(
                        f"font-size:10px; color:{ev0_color}; background:transparent; padding:1px 3px;"
                    )
                    pfl.addWidget(pill)
                    cl.addWidget(pill_frame)
                    cl.addStretch()
                else:
                    cl.addStretch()

                rl.addWidget(cell, 1)

            vl.addWidget(row_w)

        return w

    def _on_week_slot_click(self, ds: str, slot: str) -> None:
        if not self._emit({"intent": "slot_click", "view": "week", "date": ds, "time": slot}):
            return
        # optimistic update
        slots = self._selected_week_slots()
        ex_day = slots[0].get("date") if slots else None
        if ex_day and ex_day != ds:
            slots = []
        entry = {"date": ds, "time": slot}
        found = any(s["date"] == ds and s["time"] == slot for s in slots)
        slots = [s for s in slots if not (s["date"] == ds and s["time"] == slot)] if found else slots + [entry]
        self._props["selected_slots"] = slots
        self._refresh()

    # ── day view ───────────────────────────────────────────────────────────

    @staticmethod
    def _event_to_slot(ev: dict) -> str:
        """Map an event's time to its 30-min slot bucket (e.g. '09:45' → '09:30')."""
        t = str(ev.get("time") or "")
        try:
            h, m = int(t[:2]), int(t[3:5])
            return f"{h:02d}:{'30' if m >= 30 else '00'}"
        except (ValueError, IndexError):
            return t[:5]

    def _compute_ev_layout(self, evs: list, slot_idx: dict) -> list:
        """
        Assign (start_slot_idx, span, column) to each event.
        Events starting at the same or overlapping slots are placed in separate columns.
        Returns [(ev, si, span, col), ...] sorted by start.
        """
        col_ends: dict[int, int] = {}
        result = []
        n_slots = len(slot_idx)
        for ev in sorted(evs, key=lambda e: slot_idx.get(self._event_to_slot(e), 0)):
            start_slot = self._event_to_slot(ev)
            si   = slot_idx.get(start_slot, 0)
            dur  = max(30, int(ev.get("duration") or 30))
            span = max(1, (dur + 29) // 30)
            span = min(span, max(1, n_slots - si))   # clamp to available slots
            col  = 0
            while col_ends.get(col, 0) > si:
                col += 1
            col_ends[col] = si + span
            result.append((ev, si, span, col))
        return result

    def _build_day(self) -> _DayGrid:
        evs       = self._events_for_day(self._current_date)
        day_slots = self._selected_day_slots()
        slots     = self._day_slots()
        slot_idx  = {s: i for i, s in enumerate(slots)}
        ev_layout = self._compute_ev_layout(evs, slot_idx)

        return _DayGrid(
            slots         = slots,
            ev_layout     = ev_layout,
            day_slots     = day_slots,
            on_slot_click = self._on_day_slot_click,
            on_ev_click   = self._emit_event_click,
            has_ev_handler= bool(self._props.get("on_event_click")),
        )

    def _on_day_slot_click(self, slot: str) -> None:
        ds = self._current_date.toString("yyyy-MM-dd")
        if not self._emit({"intent": "slot_click", "view": "day", "date": ds, "time": slot}):
            return
        # optimistic update
        slots = self._selected_day_slots()
        if slot in slots:
            slots.discard(slot)
        else:
            slots.add(slot)
        self._props["selected_slots"] = sorted(slots)
        self._refresh()


# ─── renderer ──────────────────────────────────────────────────────────────────

class CalendarRenderer(BaseRenderer):
    component_type = "Calendar"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label":          self.PROPERTY,
            "value":          self.PROPERTY,
            "current_date":   self.PROPERTY,
            "min_date":       self.PROPERTY,
            "max_date":       self.PROPERTY,
            "date_format":    self.PROPERTY,
            "input_mask":     self.PROPERTY,
            "show_input":     self.PROPERTY,
            "view":           self.PROPERTY,
            "events":         self.PROPERTY,
            "selected_dates": self.PROPERTY,
            "selected_slots": self.PROPERTY,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        global _C
        _C = calendar_theme(app_instance=app_instance)
        max_w = props.get("max_width")
        frame, layout = _field_shell(comp_id, _literal(props.get("label")), max_width=max_w)
        cal = _AdvancedCalendarWidget(
            props,
            surface_id=surface_id,
            app_instance=app_instance,
            comp_id=comp_id,
        )
        cal.setObjectName(f"{comp_id}__advanced")
        layout.addWidget(cal)
        return frame

    def update_widget_property(self, widget, prop: str, value: Any) -> None:
        if prop == "label":
            label = self._find_first_label(widget)
            if label is not None:
                label.setText(_literal(value))
            return
        cal = widget.findChild(_AdvancedCalendarWidget, f"{widget.objectName()}__advanced")
        if cal is None:
            super().update_widget_property(widget, prop, value)
            return
        if prop in {
            "value", "current_date", "min_date", "max_date",
            "date_format", "input_mask", "show_input",
            "view", "events", "selected_dates", "selected_slots",
            "action", "on_event_click", "buttons", "time_from", "time_to",
        }:
            cal.update_prop(prop, value)
            return
        super().update_widget_property(widget, prop, value)
