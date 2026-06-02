from __future__ import annotations

from democrai.sdk.components.domains.forms.checkbox import Checkbox


class Toggle(Checkbox):
    """Toggle-style boolean input built on top of :class:`Checkbox`."""
    type = "Toggle"
