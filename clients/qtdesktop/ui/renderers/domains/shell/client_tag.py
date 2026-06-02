from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from .....state import Binding
from ....client_tags import ClientTagContext, _path_to_key
from ....tags import APP_MAIN_LIST_TAG, APP_NOTIFICATIONS_TAG
from ...base import BaseRenderer
from ...base import emit_action
from ...icon import get_icon
from ....theme.tokens import theme_token


def _literal(value: Any, fallback: str = "") -> str:
    if isinstance(value, dict):
        if "literalString" in value:
            return str(value.get("literalString") or "")
        return str(value)
    if value is None:
        return fallback
    return str(value)


def _normalize_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return "/"
    return text if text.startswith("/") else f"/{text.lstrip('/')}"


def _resolve_store_value(app_instance: Any, value: Any) -> Any:
    store = getattr(app_instance, "store", None)
    if store is None:
        return value
    if isinstance(value, dict):
        path = value.get("path")
        if path:
            return store.get(_normalize_path(str(path)), None, "auto")
    return value


def _is_item_active(app_instance: Any, item: dict[str, Any]) -> bool:
    active = item.get("active_condition")
    if isinstance(active, bool):
        return active
    if isinstance(active, (int, float)):
        return bool(active)
    if isinstance(active, str):
        return active.strip().lower() in {"1", "true", "yes", "on"}
    if not isinstance(active, dict):
        return False

    conditions = active.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        return False
    mode = str(active.get("operator", "AND")).strip().upper()
    results: list[bool] = []
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        left = _resolve_store_value(app_instance, condition.get("left"))
        right = _resolve_store_value(app_instance, condition.get("right"))
        op = str(condition.get("op", "==")).strip()
        try:
            if op == "==":
                results.append(left == right)
            elif op == "!=":
                results.append(left != right)
            elif op == ">":
                results.append(float(left) > float(right))
            elif op == "<":
                results.append(float(left) < float(right))
            elif op == ">=":
                results.append(float(left) >= float(right))
            elif op == "<=":
                results.append(float(left) <= float(right))
            elif op == "in":
                results.append(left in right)
            elif op == "contains":
                results.append(right in left)
            else:
                results.append(False)
        except Exception:
            results.append(False)
    if not results:
        return False
    return any(results) if mode == "OR" else all(results)


def _icon_name(entry: dict[str, Any]) -> str:
    raw = entry.get("icon")
    if isinstance(raw, dict):
        value = str(raw.get("iconName") or "").strip()
        return value or "ric.apps-2-line"
    value = str(raw or "").strip()
    return value or "ric.apps-2-line"


def _resolve_action_payload(
    app_instance: Any,
    raw_context: Any,
    surface_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(raw_context, dict):
        return {}
    bindings = getattr(app_instance, "bindings", None)
    if bindings is None or not hasattr(bindings, "resolve_value"):
        return raw_context

    def _resolve(value: Any) -> Any:
        if isinstance(value, dict):
            value_type = value.get("type")
            if value_type in {"store", "action", "literal"} or (
                "path" in value and "type" not in value
            ):
                try:
                    return bindings.resolve_value_for_surface(value, surface_id)
                except Exception:
                    return None
            return {k: _resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_resolve(v) for v in value]
        if isinstance(value, str):
            try:
                return bindings.resolve_value_for_surface(value, surface_id)
            except Exception:
                return value
        return value

    resolved = _resolve(raw_context)
    return resolved if isinstance(resolved, dict) else raw_context


class _TopNavOverflowWidget(QFrame):
    _BUTTON_SIZE = 45
    _ITEM_GAP = 4
    _SLOT_PX = _BUTTON_SIZE + _ITEM_GAP

    def __init__(self, surface_id: str, comp_id: str, app_instance: Any) -> None:
        super().__init__()
        self._surface_id = surface_id
        self._comp_id = comp_id
        self._app_instance = app_instance
        self._items: list[dict[str, Any]] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self._ITEM_GAP)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        self.setMinimumHeight(self._BUTTON_SIZE)
        self.setMinimumWidth(self._BUTTON_SIZE)
        self.setMaximumWidth(self._BUTTON_SIZE)
        self._last_visible_ids: tuple[str, ...] = ()
        self._last_overflow_ids: tuple[str, ...] = ()

    def set_items(self, items: list[dict[str, Any]]) -> None:
        self._items = [item for item in items if isinstance(item, dict)]
        self._rebuild()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._rebuild()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._rebuild()

    def _available_height(self) -> int:
        own = max(0, self.height())
        # Use real container height whenever available so overflow reacts
        # immediately during resize. Only fallback to sidebar estimate while
        # first layout passes still report transient tiny heights.
        if own > 8:
            return own
        sidebar = self.parentWidget()
        if sidebar is not None and sidebar.objectName() != "main_sidebar":
            sidebar = sidebar.parentWidget()
        if sidebar is None:
            return own
        logo = sidebar.findChild(QWidget, "logo_img")
        bottom = sidebar.findChild(QWidget, "bottom_nav")
        logo_h = logo.height() if logo is not None and logo.height() > 0 else (logo.sizeHint().height() if logo is not None else 0)
        bottom_h = bottom.height() if bottom is not None and bottom.height() > 0 else (bottom.sizeHint().height() if bottom is not None else 0)
        padding = 24
        estimated = max(0, sidebar.height() - logo_h - bottom_h - padding)
        return estimated

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _action_context(self, action: dict[str, Any]) -> dict[str, Any]:
        ctx = action.get("context", {})
        return ctx if isinstance(ctx, dict) else {}

    def _build_nav_button(self, entry: dict[str, Any], index: int):
        btn = QToolButton(self)
        btn.setObjectName(f"{self._comp_id}_overflow_item_{index}")
        btn.setProperty("ui_role", "vertical_button")
        is_active = _is_item_active(self._app_instance, entry)
        btn.setProperty("active", "true" if is_active else "false")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setIconSize(QSize(24, 24))
        btn.setFixedSize(self._BUTTON_SIZE, self._BUTTON_SIZE)
        btn.setToolTip(_literal(entry.get("label"), ""))
        icon_color = (
            theme_token("icon.sidebar.active", app_instance=self._app_instance)
            if is_active
            else theme_token("icon.sidebar.idle", app_instance=self._app_instance)
        )
        btn.setIcon(get_icon(_icon_name(entry), icon_color, 24))

        raw_action = entry.get("action")
        if isinstance(raw_action, dict):
            action_name = str(raw_action.get("name") or "").strip()
            context = _resolve_action_payload(
                self._app_instance,
                raw_action.get("context", {}),
                self._surface_id,
            )
        else:
            action_name = str(raw_action or "").strip()
            context = {}

        if action_name:
            btn.clicked.connect(
                lambda _checked=False, n=action_name, c=context: emit_action(
                    self._app_instance,
                    n,
                    c,
                    self._surface_id,
                    self._comp_id,
                )
            )
        return btn

    def _build_more_button(self, overflow_items: list[dict[str, Any]]) -> QToolButton:
        btn = QToolButton(self)
        btn.setProperty("ui_role", "vertical_button")
        btn.setToolTip("More")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setIcon(
            get_icon(
                "ric.more-fill",
                theme_token("icon.sidebar.idle", app_instance=self._app_instance),
                22,
            )
        )
        btn.setIconSize(QSize(22, 22))
        btn.setFixedSize(self._BUTTON_SIZE, self._BUTTON_SIZE)

        menu = QMenu(btn)
        for index, entry in enumerate(overflow_items):
            label = _literal(entry.get("label"), f"Item {index + 1}")
            icon_name = _icon_name(entry)
            action = QAction(
                get_icon(
                    icon_name,
                    theme_token("icon.sidebar.menu", app_instance=self._app_instance),
                    16,
                ),
                label,
                menu,
            )
            if _is_item_active(self._app_instance, entry):
                font = action.font()
                font.setBold(True)
                action.setFont(font)
            raw_action = entry.get("action")
            if isinstance(raw_action, dict):
                action_name = str(raw_action.get("name") or "").strip()
                context = self._action_context(raw_action)
            else:
                action_name = str(raw_action or "").strip()
                context = {}
            action.triggered.connect(
                lambda _checked=False, n=action_name, c=context: emit_action(
                    self._app_instance,
                    n,
                    c,
                    self._surface_id,
                    self._comp_id,
                )
            )
            menu.addAction(action)

        btn.clicked.connect(lambda: menu.exec(btn.mapToGlobal(btn.rect().bottomRight())))
        return btn

    def _rebuild(self) -> None:
        items = list(self._items)
        if not items:
            self._last_visible_ids = ()
            self._last_overflow_ids = ()
            self._clear()
            return
        slot_px = self._SLOT_PX
        available = self._available_height()
        if available <= 8:
            visible = items
            overflow: list[dict[str, Any]] = []
        else:
            slots = max(1, available // slot_px)
            if len(items) <= slots:
                visible = items
                overflow = []
            else:
                # Reserve one slot for "more", but keep at least one
                # real item visible (never push everything into overflow).
                visible_cap = max(1, slots - 1)
                active_index = next((i for i, item in enumerate(items) if _is_item_active(self._app_instance, item)), -1)
                visible_indices = list(range(min(visible_cap, len(items))))
                if active_index >= 0 and visible_cap > 0 and active_index not in visible_indices:
                    visible_indices[-1] = active_index
                visible_set = set(visible_indices)
                visible = [item for idx, item in enumerate(items) if idx in visible_set]
                overflow = [item for idx, item in enumerate(items) if idx not in visible_set]

        visible_ids = tuple(str(v.get("id") or f"v_{idx}") for idx, v in enumerate(visible))
        overflow_ids = tuple(str(v.get("id") or f"o_{idx}") for idx, v in enumerate(overflow))
        if visible_ids == self._last_visible_ids and overflow_ids == self._last_overflow_ids:
            return
        self._last_visible_ids = visible_ids
        self._last_overflow_ids = overflow_ids
        self._clear()

        for index, entry in enumerate(visible):
            widget = self._build_nav_button(entry, index)
            if widget is not None:
                self._layout.addWidget(widget)

        if overflow:
            self._layout.addWidget(self._build_more_button(overflow))


class _NotificationBellWidget(QWidget):
    _BTN_SIZE = 45

    def __init__(self, surface_id: str, comp_id: str, app_instance: Any) -> None:
        super().__init__()
        self._surface_id = surface_id
        self._comp_id = comp_id
        self._app_instance = app_instance

        self.setFixedSize(self._BTN_SIZE, self._BTN_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._btn = QToolButton(self)
        self._btn.setObjectName(f"{comp_id}_bell_btn")
        self._btn.setProperty("ui_role", "vertical_button")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn.setFixedSize(self._BTN_SIZE, self._BTN_SIZE)
        self._btn.setIconSize(QSize(24, 24))
        self._btn.setIcon(
            get_icon(
                "ric.notification-3-line",
                theme_token("icon.sidebar.idle", app_instance=self._app_instance),
                24,
            )
        )
        self._btn.setToolTip("Notifications")
        self._btn.clicked.connect(self._on_click)

        self._badge = QLabel(self._btn)
        self._badge.setObjectName(f"{comp_id}_bell_badge")
        self._badge.setProperty("ui_role", "notification_badge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._badge.hide()

    def set_count(self, count: int) -> None:
        count = max(0, int(count or 0))
        if count > 0:
            text = str(count) if count < 100 else "99+"
            self._badge.setText(text)
            self._badge.show()
            metrics = self._badge.fontMetrics()
            bw = max(metrics.horizontalAdvance(text) + 8, 16)
            bh = max(metrics.height() + 4, 16)
            self._badge.setFixedSize(bw, bh)
            self._badge.move(self._BTN_SIZE - bw, 0)
            self._btn.setIcon(
                get_icon(
                    "ric.notification-3-fill",
                    theme_token("icon.sidebar.active", app_instance=self._app_instance),
                    24,
                )
            )
        else:
            self._badge.hide()
            self._btn.setIcon(
                get_icon(
                    "ric.notification-3-line",
                    theme_token("icon.sidebar.idle", app_instance=self._app_instance),
                    24,
                )
            )

    def _on_click(self) -> None:
        store = getattr(self._app_instance, "store", None)
        view_path = ""
        if store is not None:
            view_path = str(
                store.get("/core/notifications/view_path", "", "auto") or ""
            ).strip()
        if not view_path:
            return
        emit_action(
            self._app_instance,
            "open_drawer",
            {
                "path": view_path,
                "position": "right",
                "dim": 680,
            },
            self._surface_id,
            self._comp_id,
        )


class ClientTagRenderer(BaseRenderer):
    component_type = "ClientTag"

    def render(
        self,
        props: dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        container = QFrame()
        container.setObjectName(comp_id)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tag = str(props.get("tag", "")).strip()
        registry = getattr(app_instance.renderer, "client_tag_registry", None)
        if not tag or registry is None:
            return container

        definition = registry.get(tag)
        if definition is None:
            return container

        ctx = ClientTagContext(
            surface_id=surface_id,
            component_id=comp_id,
            props=props,
            app_instance=app_instance,
        )

        if tag == APP_MAIN_LIST_TAG:
            container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            container.setMinimumHeight(45)
            container.setMinimumWidth(45)
            container.setMaximumWidth(45)
            panel = _TopNavOverflowWidget(surface_id, comp_id, app_instance)
            layout.addWidget(panel)

            def populate_main(_: Any = None) -> None:
                items = ctx.get_store_value("/system/modules/top", [], scope="global")
                panel.set_items(items if isinstance(items, list) else [])

            populate_main()
            for path in definition.observe_paths:
                key = _path_to_key(path)
                app_instance.binder.bind(
                    Binding(
                        key=key,
                        widget=container,
                        set_widget=populate_main,
                        transform_from_store=lambda value: value,
                    )
                )
            return container

        if tag == APP_NOTIFICATIONS_TAG:
            container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            container.setFixedSize(45, 45)
            bell = _NotificationBellWidget(surface_id, comp_id, app_instance)
            layout.addWidget(bell)

            def update_bell_count(_: Any = None) -> None:
                count = ctx.get_store_value(
                    "/core/notifications/pending_count",
                    0,
                    scope="global",
                )
                bell.set_count(int(count or 0))

            update_bell_count()
            for path in definition.observe_paths:
                key = _path_to_key(path)
                app_instance.binder.bind(
                    Binding(
                        key=key,
                        widget=container,
                        set_widget=update_bell_count,
                        transform_from_store=lambda value: value,
                    )
                )
            return container

        def populate(_: Any = None) -> None:
            self._populate_container(container, ctx, definition.resolve(ctx), app_instance)

        populate()

        for path in definition.observe_paths:
            key = _path_to_key(path)
            app_instance.binder.bind(
                Binding(
                    key=key,
                    widget=container,
                    set_widget=populate,
                    transform_from_store=lambda value: value,
                )
            )

        return container

    def _populate_container(
        self,
        container: QFrame,
        ctx: ClientTagContext,
        components: list[dict[str, Any]],
        app_instance: Any,
    ) -> None:
        layout = container.layout()
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for component in components:
            widget = app_instance.renderer.build_widget(
                ctx.surface_id,
                app_instance.surfaces,
                comp_def=component,
                app_instance=app_instance,
            )
            if widget is not None:
                layout.addWidget(widget)
