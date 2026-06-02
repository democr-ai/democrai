from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QGridLayout,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)


def replace_widget_instance(
    old_widget: Any,
    new_widget: Any,
    *,
    qtabwidget_cls: Any,
    qsplitter_cls: Any,
    qscrollarea_cls: Any,
) -> bool:
    parent = old_widget.parentWidget() if hasattr(old_widget, "parentWidget") else None
    if parent is None:
        return False

    if isinstance(parent, qtabwidget_cls):
        index = parent.indexOf(old_widget)
        if index < 0:
            return False
        tab_label = parent.tabText(index)
        current_index = parent.currentIndex()   # preserve active tab
        parent.removeTab(index)
        old_widget.setParent(None)
        old_widget.deleteLater()
        parent.insertTab(index, new_widget, tab_label)
        parent.setCurrentIndex(current_index)   # restore, not force-switch
        return True

    if isinstance(parent, qsplitter_cls):
        index = parent.indexOf(old_widget)
        if index < 0:
            return False
        parent.insertWidget(index, new_widget)
        old_widget.setParent(None)
        old_widget.deleteLater()
        return True

    if isinstance(parent, qscrollarea_cls) and hasattr(parent, "widget") and hasattr(parent, "setWidget"):
        if parent.widget() is not old_widget:
            return False
        old_widget.setParent(None)
        old_widget.deleteLater()
        parent.setWidget(new_widget)
        return True

    parent_layout = parent.layout() if hasattr(parent, "layout") else None
    if parent_layout is None:
        return False

    index = -1
    stretch = 0
    for i in range(parent_layout.count()):
        item = parent_layout.itemAt(i)
        if item is not None and item.widget() is old_widget:
            index = i
            if isinstance(parent_layout, QBoxLayout):
                stretch = parent_layout.stretch(i)
            break
    if index < 0:
        return False

    parent_layout.removeWidget(old_widget)
    old_widget.hide()
    old_widget.setParent(None)
    old_widget.deleteLater()
    if isinstance(parent_layout, QBoxLayout):
        parent_layout.insertWidget(index, new_widget, stretch)
    elif isinstance(parent_layout, QGridLayout):
        parent_layout.addWidget(new_widget)
    elif hasattr(parent_layout, "insertWidget"):
        try:
            parent_layout.insertWidget(index, new_widget)
        except TypeError:
            parent_layout.addWidget(new_widget)
    else:
        parent_layout.addWidget(new_widget)
    return True


def rerender_component(
    controller: Any,
    comp_id: str,
    *,
    qscrollarea_cls: Any,
    qtabwidget_cls: Any,
    qsplitter_cls: Any,
) -> None:
    widget = controller.window._get_widget_by_id(comp_id)
    if not widget:
        controller.window._debug(f"rerender_component failed: widget {comp_id} not found")
        return

    comp_def = None
    surface_id = "main"
    for sid, surface in controller.window.surfaces.items():
        if comp_id in surface.get("components", {}):
            comp_def = surface["components"][comp_id]
            surface_id = sid
            break

    if not comp_def:
        controller.window._debug(
            f"rerender_component failed: definition for {comp_id} not found"
        )
        return

    resolved_comp_def = controller.window.renderer.resolve_bindings(comp_def)
    c_type = list(resolved_comp_def["component"].keys())[0]
    renderer = controller.window.renderer.registry.get(c_type)
    if not renderer:
        return

    rebuilt_widget = controller.window.renderer.build_widget(
        surface_id,
        controller.window.surfaces,
        comp_id=comp_id,
        app_instance=controller.window,
        seen_dialogs=set(),
    )
    if rebuilt_widget is not None and rebuilt_widget is not widget:
        if replace_widget_instance(
            widget,
            rebuilt_widget,
            qtabwidget_cls=qtabwidget_cls,
            qsplitter_cls=qsplitter_cls,
            qscrollarea_cls=qscrollarea_cls,
        ):
            controller._mark_widget_index_dirty()
            controller.window._debug(f"Selective re-render completed for {comp_id} (replaced)")
            return

    comp_props = resolved_comp_def["component"][c_type]
    layout = widget.layout()
    if layout:
        controller.clear_layout(cast(QVBoxLayout, layout))
    elif isinstance(widget, qscrollarea_cls):
        cw = widget.widget()
        if cw and cw.layout():
            l = cw.layout()
            if l:
                controller.clear_layout(cast(QVBoxLayout, l))
    elif isinstance(widget, qtabwidget_cls):
        widget.clear()
    elif isinstance(widget, qsplitter_cls):
        count = widget.count()
        for i in range(count - 1, -1, -1):
            w = widget.widget(i)
            if w:
                w.setParent(None)
                w.deleteLater()

    controller.window.renderer.populate_children(
        widget,
        comp_props,
        comp_props,
        resolved_comp_def,
        surface_id,
        controller.window.surfaces,
        None,
        controller.window,
        None,
        renderer,
        comp_id,
    )
    controller._mark_widget_index_dirty()
    controller.window._debug(f"Selective re-render completed for {comp_id}")


def render_tree(controller: Any, surface_id: str, root_id: str, *, slide_fn: Any, fade_in_fn: Any) -> None:
    controller.window._pending_property_updates.clear()
    if controller.window._property_flush_timer.isActive():
        controller.window._property_flush_timer.stop()

    target_layout = None
    if surface_id == "main":
        controller._clear_main_surface_container()
        target_layout = controller.window.ui_layout
    else:
        host = controller.window._get_surface_host(surface_id)
        if surface_id == "modal" and (not host or not host.layout()):
            # Modal surface is hostless: dialogs are top-level widgets.
            seen_dialogs: set[str] = set()
            _ = controller.window.renderer.build_widget(
                surface_id,
                controller.window.surfaces,
                comp_id=root_id,
                app_instance=controller.window,
                seen_dialogs=seen_dialogs,
            )
            return
        if not host or not host.layout():
            controller.window._debug(
                f"render_tree deferred: no host found for surface {surface_id}"
            )
            controller.window._pending_surface_mounts[surface_id] = root_id
            return
        if surface_id == "drawer":
            if hasattr(host, "show"):
                host.show()
            if hasattr(host, "raise_"):
                host.raise_()
            update_host_geometry = getattr(controller.window, "_update_surface_host_geometry", None)
            if callable(update_host_geometry):
                update_host_geometry()
        controller.clear_layout(cast(QVBoxLayout, host.layout()))
        target_layout = host.layout()
    controller._mark_widget_index_dirty()

    seen_dialogs: set[str] = set()
    root_widget = controller.window.renderer.build_widget(
        surface_id,
        controller.window.surfaces,
        comp_id=root_id,
        app_instance=controller.window,
        seen_dialogs=seen_dialogs,
    )
    if root_widget:
        animation_target = root_widget
        if surface_id == "drawer":
            try:
                drawer_scroll_top_margin = max(
                    0,
                    int(getattr(controller.window, "_drawer_scroll_top_margin", 20)),
                )
            except Exception:
                drawer_scroll_top_margin = 20

            drawer_content_padding = 12
            drawer_shell = QWidget()
            drawer_shell.setObjectName("global_drawer_shell")
            drawer_shell_layout = QVBoxLayout(drawer_shell)
            drawer_shell_layout.setContentsMargins(0, 0, 0, 0)
            drawer_shell_layout.setSpacing(0)

            drawer_scroll = QScrollArea(drawer_shell)
            drawer_scroll.setObjectName("global_drawer_scroll")
            drawer_scroll.setWidgetResizable(True)
            drawer_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

            drawer_scroll_content = QWidget(drawer_scroll)
            drawer_scroll_content.setObjectName("global_drawer_scroll_content")
            drawer_scroll_content.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            drawer_scroll_content_layout = QVBoxLayout(drawer_scroll_content)
            drawer_scroll_content_layout.setContentsMargins(
                drawer_content_padding,
                drawer_scroll_top_margin,
                drawer_content_padding,
                drawer_content_padding,
            )
            drawer_scroll_content_layout.setSpacing(0)
            drawer_surface = controller.window.surfaces.get("drawer", {})
            drawer_components = (
                drawer_surface.get("components", {})
                if isinstance(drawer_surface, dict)
                else {}
            )
            root_def = (
                drawer_components.get(root_id)
                if isinstance(drawer_components, dict)
                else None
            )
            root_props: dict[str, Any] = {}
            if isinstance(root_def, dict):
                root_component = root_def.get("component", {})
                if isinstance(root_component, dict) and root_component:
                    root_props = next(iter(root_component.values()))
                    if not isinstance(root_props, dict):
                        root_props = {}

            if root_props.get("stretch") is True:
                if hasattr(root_widget, "setSizePolicy"):
                    root_widget.setSizePolicy(
                        QSizePolicy.Policy.Ignored,
                        QSizePolicy.Policy.Expanding,
                    )
                drawer_scroll_content_layout.addWidget(root_widget, 1)
            else:
                if hasattr(root_widget, "sizePolicy") and hasattr(root_widget, "setSizePolicy"):
                    root_policy = root_widget.sizePolicy()
                    root_widget.setSizePolicy(
                        QSizePolicy.Policy.Ignored,
                        QSizePolicy.Policy.Preferred,
                    )
                drawer_scroll_content_layout.addWidget(root_widget)
                drawer_scroll_content_layout.addStretch(1)
            drawer_scroll.setWidget(drawer_scroll_content)

            drawer_shell_layout.addWidget(drawer_scroll, 1)
            target_layout.addWidget(drawer_shell, 1)
            animation_target = drawer_shell
        else:
            target_layout.addWidget(root_widget, 1)

        if (
            surface_id == "drawer"
            and hasattr(animation_target, "pos")
            and hasattr(animation_target, "width")
            and hasattr(animation_target, "height")
        ):
            drawer_surface = controller.window.surfaces.get("drawer", {})
            drawer_options = drawer_surface.get("options", {}) if isinstance(drawer_surface, dict) else {}
            position = str(drawer_options.get("position") or "right").strip().lower()
            end_pos = animation_target.pos()
            if position == "left":
                start_pos = QPoint(end_pos.x() - max(animation_target.width(), 48), end_pos.y())
            elif position == "top":
                start_pos = QPoint(end_pos.x(), end_pos.y() - max(animation_target.height(), 48))
            elif position == "bottom":
                start_pos = QPoint(end_pos.x(), end_pos.y() + max(animation_target.height(), 48))
            else:
                start_pos = QPoint(end_pos.x() + max(animation_target.width(), 48), end_pos.y())
            slide_fn(animation_target, start=start_pos, end=end_pos, duration=220)
            fade_in_fn(animation_target, duration=220, start=0.0, end=1.0)
        
        drawer_close_btn = getattr(controller.window, "_drawer_close_btn", None)
        if drawer_close_btn is not None and hasattr(drawer_close_btn, "raise_"):
            drawer_close_btn.raise_()

    active = controller.window.renderer.active_dialogs.get(surface_id, {})
    to_remove = []
    for did, dialog in active.items():
        if did not in seen_dialogs:
            dialog.close()
            to_remove.append(did)

    for did in to_remove:
        del active[did]
    controller._mark_widget_index_dirty()

    if surface_id == "main":
        pending = dict(controller.window._pending_surface_mounts)
        controller.window._pending_surface_mounts.clear()
        for pending_surface_id, pending_root_id in pending.items():
            controller.window._debug(
                f"retrying deferred render for surface {pending_surface_id}"
            )
            controller.render_tree(pending_surface_id, pending_root_id)
        rerender_mounted_subsurfaces(controller)


def rerender_mounted_subsurfaces(controller: Any) -> None:
    for mounted_surface_id, mounted_root_id in list(controller.window._surface_roots.items()):
        if mounted_surface_id == "main":
            continue
        if mounted_surface_id not in controller.window.surfaces:
            continue
        controller.window._debug(
            f"reattaching mounted surface {mounted_surface_id} after main rerender"
        )
        controller.render_tree(mounted_surface_id, mounted_root_id)


def animate_drawer_exit(controller: Any, host: Any, *, slide_fn: Any, fade_out_fn: Any) -> None:
    def _clear_and_hide() -> None:
        if layout is not None and hasattr(layout, "count"):
            controller.clear_layout(cast(QVBoxLayout, layout))
        if hasattr(host, "hide"):
            host.hide()

    layout = host.layout()
    if not layout or not hasattr(layout, "count") or not hasattr(layout, "itemAt"):
        _clear_and_hide()
        return
    if layout.count() <= 0:
        _clear_and_hide()
        return

    item = layout.itemAt(0)
    drawer_widget = item.widget() if item is not None and hasattr(item, "widget") else None
    if (
        drawer_widget is None
        or not hasattr(drawer_widget, "pos")
        or not hasattr(drawer_widget, "width")
        or not hasattr(drawer_widget, "height")
    ):
        _clear_and_hide()
        return

    start_pos = drawer_widget.pos()
    if not isinstance(start_pos, QPoint):
        _clear_and_hide()
        return

    drawer_surface = controller.window.surfaces.get("drawer", {})
    drawer_options = drawer_surface.get("options", {}) if isinstance(drawer_surface, dict) else {}
    position = str(drawer_options.get("position") or "right").strip().lower()
    if position == "left":
        end_pos = QPoint(start_pos.x() - max(drawer_widget.width(), 48), start_pos.y())
    elif position == "top":
        end_pos = QPoint(start_pos.x(), start_pos.y() - max(drawer_widget.height(), 48))
    elif position == "bottom":
        end_pos = QPoint(start_pos.x(), start_pos.y() + max(drawer_widget.height(), 48))
    else:
        end_pos = QPoint(start_pos.x() + max(drawer_widget.width(), 48), start_pos.y())
    slide_fn(drawer_widget, start=QPoint(start_pos), end=end_pos, duration=180)
    fade_out_fn(
        drawer_widget,
        duration=180,
        start=1.0,
        end=0.0,
        hide_on_finish=False,
        finished=_clear_and_hide,
    )
