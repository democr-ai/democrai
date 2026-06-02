from __future__ import annotations


class DesktopActionBridge:
    """Translate desktop user actions into application commands."""

    def __init__(self, handle_user_action) -> None:
        self.handle_user_action = handle_user_action

    def on_action(self, action) -> None:
        self.handle_user_action.execute(action)
