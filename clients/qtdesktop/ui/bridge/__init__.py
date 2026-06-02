"""Desktop bridge adapters for desktop UI controllers."""

from .action_bridge import DesktopActionBridge
from .inbound_bridge import DesktopInboundBridge

__all__ = ["DesktopActionBridge", "DesktopInboundBridge"]
