from typing import List, Dict, Any, Optional
from democrai.sdk.components.base import Component


class DataTable(Component):
    """A model-driven data table with editing, pagination, filtering, selection and row actions."""

    type = "DataTable"

    def __init__(
        self,
        id: str,
        model: Optional[List[Dict[str, Any]]] = None,
        rows: Optional[List[Dict[str, Any]]] = None,
        page: int = 0,
        page_size: int = 25,
        total_rows: int = 0,
        remote_service: Optional[str | Dict[str, Any]] = None,
        pagination: Optional[bool] = None,
        on_page_change: Optional[str | Dict[str, Any]] = None,
        on_cell_edit: Optional[str | Dict[str, Any]] = None,
        on_row_add: Optional[str | Dict[str, Any]] = None,
        on_row_delete: Optional[str | Dict[str, Any]] = None,
        on_filter_change: Optional[str | Dict[str, Any]] = None,
        show_row_numbers: bool = False,
        selectable: bool = False,
        row_actions: Optional[List[Dict[str, Any]]] = None,
        selection_actions: Optional[List[Dict[str, Any]]] = None,
        paginated: bool = True,
        virtual: bool = False,
        auto_refresh: Optional[int] = None,
        sort_field: Optional[str] = None,
        sort_direction: str = "asc",
    ):
        super().__init__(id)
        self.mutable_collection("rows").allow(
            "page.set",
            "page_size.set",
            "total_rows.set",
            "sort.set",
            "filters.set",
        ).interactive()
        effective_paginated = paginated if pagination is None else pagination
        self.set_prop("model", model if model is not None else [])
        self.set_prop("rows", rows if rows is not None else [])
        self.set_prop("page", page)
        self.set_prop("page_size", page_size)
        self.set_prop("total_rows", total_rows)
        self.set_prop("show_row_numbers", show_row_numbers)
        self.set_prop("selectable", selectable)
        self.set_prop("paginated", effective_paginated)
        self.set_prop("pagination", effective_paginated)
        self.set_prop("virtual", virtual)

        normalized_remote_service: Optional[Dict[str, Any]] = None
        if remote_service:
            if isinstance(remote_service, str):
                normalized_remote_service = {"name": remote_service, "context": {}}
            elif isinstance(remote_service, dict):
                normalized_remote_service = {
                    "name": remote_service.get("name", ""),
                    "context": remote_service.get("context") or {},
                }
            if normalized_remote_service and normalized_remote_service.get("name"):
                self.set_prop("remote_service", normalized_remote_service)

        if auto_refresh is not None and auto_refresh > 0:
            self.set_prop("auto_refresh", auto_refresh)
        if row_actions:
            self.set_prop("row_actions", row_actions)
        if selection_actions:
            self.set_prop("selection_actions", selection_actions)
        if sort_field:
            self.set_prop(
                "sort",
                {
                    "field": sort_field,
                    "direction": (
                        "desc"
                        if sort_direction.strip().lower() == "desc"
                        else "asc"
                    ),
                },
            )

        page_change_service = self._normalize_action(
            on_page_change or (normalized_remote_service.get("name") if normalized_remote_service else None)
        )
        filter_change_service = self._normalize_action(
            on_filter_change or (normalized_remote_service.get("name") if normalized_remote_service else None)
        )

        if page_change_service:
            self.set_prop("on_page_change", page_change_service)
        if on_cell_edit:
            self.set_prop("on_cell_edit", self._normalize_action(on_cell_edit))
        if on_row_add:
            self.set_prop("on_row_add", self._normalize_action(on_row_add))
        if on_row_delete:
            self.set_prop("on_row_delete", self._normalize_action(on_row_delete))
        if filter_change_service:
            self.set_prop("on_filter_change", filter_change_service)

    @staticmethod
    def _normalize_action(action: Optional[str | Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if isinstance(action, str) and action.strip():
            return {"name": action.strip(), "context": {}}
        if isinstance(action, dict):
            name = str(action.get("name") or "").strip()
            if not name:
                return None
            payload = dict(action)
            payload["name"] = name
            if not isinstance(payload.get("context"), dict):
                payload["context"] = {}
            return payload
        return None
