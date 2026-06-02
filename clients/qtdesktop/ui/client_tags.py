from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import json
import os
from .tags import (
    APP_BOTTOM_MAIN_LIST_TAG,
    APP_LANGUAGE_TAG,
    APP_MAIN_LIST_TAG,
    APP_NOTIFICATIONS_TAG,
)

ICON_GALLERY_TAG = "icon_gallery"

_ICONS_CACHE = None


def _get_icons_list() -> list[str]:
    global _ICONS_CACHE
    if _ICONS_CACHE is not None:
        return _ICONS_CACHE

    try:
        from ..utils.paths import resolve_resource

        path = resolve_resource("fonts/remixicon-custom.json")

        # Fallback if first resolve failed (sometimes assets prefix is needed explicitly)
        # if not path or not os.path.exists(path):
        #    path = resolve_resource("clients/qtdesktop/assets/fonts/remixicon-custom.json")

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _ICONS_CACHE = sorted(list(data.keys()))
        else:
            # Last resort: try walking relative to this file
            base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            path = os.path.join(base_dir, "assets", "fonts", "remixicon-custom.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    _ICONS_CACHE = sorted(list(data.keys()))
    except Exception as e:
        print(f"[ClientTag:IconGallery] Error loading icons: {e}")
        _ICONS_CACHE = []
    return _ICONS_CACHE


def _path_to_key(path: str) -> str:
    return path if path.startswith("/") else f"/{path.lstrip('/')}"


@dataclass(frozen=True)
class ClientTagContext:
    surface_id: str
    component_id: str
    props: dict[str, Any]
    app_instance: Any

    def get_store_value(
        self,
        path: str,
        default: Any = None,
        *,
        scope: str = "auto",
    ) -> Any:
        store = getattr(self.app_instance, "store", None)
        if store is None:
            return default
        return store.get(_path_to_key(path), default, scope)


@dataclass(frozen=True)
class ClientTagDefinition:
    resolve: Callable[[ClientTagContext], list[dict[str, Any]]]
    observe_paths: tuple[str, ...] = ()


class ClientTagRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ClientTagDefinition] = {}

    def register(
        self,
        tag: str,
        resolve: Callable[[ClientTagContext], list[dict[str, Any]]],
        *,
        observe_paths: tuple[str, ...] = (),
    ) -> None:
        self._definitions[tag] = ClientTagDefinition(
            resolve=resolve,
            observe_paths=observe_paths,
        )

    def get(self, tag: str) -> ClientTagDefinition | None:
        return self._definitions.get(tag)


def _safe_suffix(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "item"


def _component(component_id: str, component_type: str, props: dict[str, Any], children: list[Any] | None = None) -> dict[str, Any]:
    return {
        "id": component_id,
        "component": {component_type: props},
        "children": {"explicitList": children or []},
    }


def _button(
    component_id: str,
    label: str = "",
    *,
    icon: str | None = None,
    action: Any = None,
    variant: str = "default",
    mode: str = "solid",
    btnsize: str = "normal",
    shape: str = "default",
    params: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    props: dict[str, Any] = {
        "label": {"literalString": label},
        "variant": variant,
        "mode": mode,
        "btnsize": btnsize,
        "shape": shape,
    }
    if icon:
        props["icon"] = {"iconName": icon}
    if action is not None:
        props["action"] = (
            {"name": action, "context": params if params is not None else {}}
            if isinstance(action, str)
            else action
        )
    if extra:
        props.update(extra)
    return _component(component_id, "Button", props)


def _build_nav_item_template(component_id: str) -> dict[str, Any]:
    item = _button(
        f"{component_id}_item",
        "",
        mode="ghost",
        btnsize="large",
        shape="round",
        icon="{{icon}}",
        extra={
            "active": "{{active_condition}}",
            "focusable": False,
            "style": "margin-bottom: 2px",
        },
    )
    item["component"]["Button"]["action"] = "{{action}}"
    return item


def _build_nav_list(
    tag: str,
    component_id: str,
    items: list[dict[str, Any]],
    *,
    style: str | None = None,
) -> dict[str, Any]:
    props = {
        "dataSource": {"type": "inline", "data": items},
        "itemTemplate": _build_nav_item_template(component_id),
        "template": "custom",
        "orientation": "vertical",
        "selectable": False,
        "itemActions": [],
        "selectedItemsActionLabel": "Apply to selected",
    }
    component = _component(
        f"{component_id}_{_safe_suffix(tag)}",
        "List",
        props,
    )
    if style:
        props["style"] = style
    component["children"]["template"] = props["itemTemplate"]
    return component


def _resolve_app_main_list(ctx: ClientTagContext) -> list[dict[str, Any]]:
    items = ctx.get_store_value("/system/modules/top", [], scope="global")
    if not isinstance(items, list):
        return []
    filtered_items = [item for item in items if isinstance(item, dict)]
    return [_build_nav_list(APP_MAIN_LIST_TAG, ctx.component_id, filtered_items)]


def _resolve_app_bottom_main_list(ctx: ClientTagContext) -> list[dict[str, Any]]:
    items = ctx.get_store_value("/system/modules/bottom", [], scope="global")
    if not isinstance(items, list):
        return []
    filtered_items = [item for item in items if isinstance(item, dict)]
    language_controls = _resolve_language(ctx)

    current_theme = str(
        ctx.get_store_value("/system/client/theme", "dark", scope="global") or "dark"
    ).lower()
    if current_theme not in {"dark", "light"}:
        current_theme = "dark"

    theme_toggle = _component(
        f"{ctx.component_id}_theme",
        "Toggle",
        {
            "label": {"literalString": ""},
            "checked": current_theme == "light",
            "action": {"name": "client.set_theme", "context": {}},
            "icon_on": "ric.sun-line",
            "icon_off": "ric.moon-line",
            "margin_left": 6,
            "style": "margin-top: 8px;",
        },
    )

    return [
        _build_nav_list(
            APP_BOTTOM_MAIN_LIST_TAG,
            ctx.component_id,
            filtered_items,
            style="margin-bottom: 8px;",
        ),
        theme_toggle,
        *language_controls,
    ]


def _resolve_language(ctx: ClientTagContext) -> list[dict[str, Any]]:
    raw_language_options = ctx.get_store_value(
        "/core/supported_languages",
        [],
        scope="global",
    )
    language_options = (
        [
            item
            for item in raw_language_options
            if isinstance(item, dict) and item.get("label") and item.get("value")
        ]
        if isinstance(raw_language_options, list)
        else []
    )
    current_language = str(
        ctx.get_store_value("/core/user/language", "en", scope="global") or "en"
    ).lower()
    if not language_options:
        return []
    language_select = _component(
        f"{ctx.component_id}_language",
        "Select",
        {
            "label": {"literalString": ""},
            "options": language_options,
            "value": current_language,
            "placeholder": "",
            "multiple": False,
            "searchable": False,
            "max_width": 68,
            "action": {"name": "set_user_language", "context": {}},
            "style": "margin-top: 8px; min-width: 68px; max-width: 68px; font-size: 11px;",
        },
    )
    return [language_select]


ICON_CONTROLS_TAG = "icon_controls"
ICON_GALLERY_TAG = "icon_gallery"


def _resolve_icon_controls(ctx: ClientTagContext) -> list[dict[str, Any]]:
    search_field = _component(
        "desktop_icon_search",
        "TextField",
        {
            "label": {"literalString": ""},
            "value": {"type": "store", "path": "/temp/icon_search"},
            "placeholder": "Search icons...",
            "password": False,
            "action": {"name": "client.reset_page", "context": {}},
            "style": "flex: 1;",
        },
    )
    prev_btn = _button(
        "btn_prev",
        icon="ric.arrow-left-s-line",
        action="client.prev_page",
        shape="round",
    )
    next_btn = _button(
        "btn_next",
        icon="ric.arrow-right-s-line",
        action="client.next_page",
        shape="round",
    )
    return [
        _component(
            "desktop_controls",
            "Row",
            {
                "spacing": 10,
                "style": "margin-bottom: 12px; align-items: center;",
            },
            [search_field, prev_btn, next_btn],
        )
    ]


def _resolve_icon_gallery(ctx: ClientTagContext) -> list[dict[str, Any]]:
    search = str(ctx.get_store_value("/temp/icon_search", "")).lower()
    page = int(ctx.get_store_value("/temp/icon_page", 0))

    icons = _get_icons_list()
    if search:
        icons = [i for i in icons if search in i.lower()]

    limit = 80
    total_pages = (len(icons) + limit - 1) // limit if icons else 1
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0

    start = page * limit
    end = start + limit
    display_icons = icons[start:end]

    grid_children = []
    for icon_name in display_icons:
        qualified_name = f"ric.{icon_name}"
        btn = _button(
            f"btn_{icon_name}",
            icon=qualified_name,
            action="client.copy_to_clipboard",
            params={"text": qualified_name, "title": "Icon copied"},
            shape="round",
            variant="default",
            mode="ghost",
            extra={
                "tooltip": qualified_name,
                "style": "min-width: 32px; min-height: 32px; max-width: 32px; max-height: 32px; padding: 0; margin: 1px;",
            },
        )
        grid_children.append(btn)

    grid = _component("icon_grid", "Flow", {"spacing": 4}, grid_children)
    info_text = _component(
        "pagination_info",
        "Text",
        {
            "text": {
                "literalString": f"Page {page + 1} of {total_pages} ({len(icons)} icons)"
            },
            "style": "font-size: 13px; opacity: 0.7;",
        },
    )
    root = _component("icon_gallery_root", "Column", {"spacing": 10}, [grid, info_text])
    return [root]


def _resolve_notifications(_ctx: ClientTagContext) -> list[dict[str, Any]]:
    # The desktop renderer handles this tag with a custom widget; resolver is unused.
    return []


def build_default_client_tag_registry() -> ClientTagRegistry:
    registry = ClientTagRegistry()
    registry.register(
        APP_MAIN_LIST_TAG,
        _resolve_app_main_list,
        observe_paths=("/system/modules/top",),
    )
    registry.register(
        APP_BOTTOM_MAIN_LIST_TAG,
        _resolve_app_bottom_main_list,
        observe_paths=(
            "/system/modules/bottom",
            "/core/user/language",
            "/core/supported_languages",
            "/system/client/theme",
        ),
    )
    registry.register(
        APP_LANGUAGE_TAG,
        _resolve_language,
        observe_paths=(
            "/core/user/language",
            "/core/supported_languages",
        ),
    )
    registry.register(
        ICON_CONTROLS_TAG,
        _resolve_icon_controls,
    )
    registry.register(
        ICON_GALLERY_TAG,
        _resolve_icon_gallery,
        observe_paths=("/temp/icon_search", "/temp/icon_page"),
    )
    registry.register(
        APP_NOTIFICATIONS_TAG,
        _resolve_notifications,
        observe_paths=(
            "/core/notifications/pending_count",
            "/core/notifications/view_path",
        ),
    )
    return registry
