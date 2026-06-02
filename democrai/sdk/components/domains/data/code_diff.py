from __future__ import annotations

from typing import Any, Optional

from democrai.sdk.components.base import Component


def _is_binding(value: Any) -> bool:
    return isinstance(value, dict) and (
        value.get("type") in {"store", "data", "action", "literal"} or "path" in value
    )


class CodeDiff(Component):
    """Structured code-diff component for file revisions and hunks."""
    type = "CodeDiff"

    def __init__(
        self,
        id: str,
        *,
        file_path: str = "",
        hunks: Optional[list[dict[str, Any]]] = None,
        title: str = "",
        old_revision: str = "",
        new_revision: str = "",
        show_line_numbers: bool = True,
    ):
        super().__init__(id)
        self.set_prop("hunks", hunks if hunks is not None else [])
        self.set_prop(
            "showLineNumbers",
            show_line_numbers,
        )
        if file_path:
            self.set_prop("filePath", file_path)
        if title:
            self.set_prop("title", title)
        if old_revision:
            self.set_prop("oldRevision", old_revision)
        if new_revision:
            self.set_prop("newRevision", new_revision)
