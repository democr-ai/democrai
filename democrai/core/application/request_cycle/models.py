from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


def infer_request_kind(message: Dict[str, Any]) -> str:
    """
    Heuristically determines the kind of request based on the message content.

    :param message: The raw message dictionary.
    :return: A string identifying the request kind (e.g., 'userAction', 'ping').
    """
    if "userAction" in message:
        return "userAction"
    if "bindingAction" in message:
        return "bindingAction"
    return str(message.get("type") or "unknown")


@dataclass(frozen=True)
class RequestEnvelope:
    """
    Wraps an incoming transport message with parsed metadata.

    The envelope provides convenient access to the request ID, the raw message,
    and the inferred request kind.
    """
    request_id: str
    message: Dict[str, Any]
    kind: str

    @classmethod
    def from_message(cls, message: Dict[str, Any]) -> "RequestEnvelope":
        """
        Creates a RequestEnvelope from a raw message dictionary.

        :param message: The incoming message.
        :return: A new RequestEnvelope instance.
        """
        payload = dict(message)
        return cls(
            request_id=str(payload.get("request_id") or ""),
            message=payload,
            kind=infer_request_kind(payload),
        )

    @property
    def is_ping(self) -> bool:
        return self.message.get("type") == "ping" or "ping" in self.message

    @property
    def is_init(self) -> bool:
        return self.message.get("type") == "init" or not self.message

    @property
    def has_user_action(self) -> bool:
        return "userAction" in self.message

    @property
    def has_binding_action(self) -> bool:
        return "bindingAction" in self.message
