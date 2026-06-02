from __future__ import annotations

from typing import Any, Dict, List, Optional

from democrai.sdk.components.domains.forms.select import Select


class Combobox(Select):
    """Searchable single-select input built on top of :class:`Select`."""
    type = "Combobox"

    def __init__(
        self,
        id: str,
        label: str = "",
        options: Optional[List[Dict[str, Any]]] = None,
        value: Any = "",
        placeholder: str = "",
        max_width: Optional[int] = None,
        action: Optional[str] = None,
        params: Optional[dict] = None,
    ):
        super().__init__(
            id=id,
            label=label,
            options=options,
            value=value,
            placeholder=placeholder,
            multiple=False,
            searchable=True,
            max_width=max_width,
            action=action,
            params=params,
        )
