"""
ConnectionRegistry — maps (user_id, organization_id) ↔ (bus, client_id) for targeted message delivery.

Used by the TaskManager to push background task updates to the correct client(s),
and by the Network coordinator to flush pending notifications on reconnect.
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from threading import Lock
from democrai.core.infrastructure.network.contracts import BusProvider


ScopeKey = Tuple[int, Optional[int]]


def _scope_key(user_id: int, organization_id: Optional[int] = None) -> ScopeKey:
    return (user_id, organization_id)


class ConnectionRegistry:
    """
    Thread-safe bidirectional registry:
    - (user_id, organization_id) → List[(bus, client_id)] — for scoped delivery
    - (bus_id, client_id) → (user_id, organization_id)    — for cleanup on disconnect
    """

    def __init__(self):
        self._user_connections: Dict[ScopeKey, List[Tuple[BusProvider, Any]]] = {}
        self._client_to_user: Dict[Tuple[int, Any], ScopeKey] = {}
        self._lock = Lock()

    def register(
        self,
        user_id: int,
        bus: BusProvider,
        client_id: Any,
        organization_id: Optional[int] = None,
    ) -> None:
        """Register a connection for a scoped user identity. Called after successful JWT auth."""
        key = (id(bus), client_id)
        scope = _scope_key(user_id, organization_id)
        with self._lock:
            # Remove any previous mapping for this client
            old_scope = self._client_to_user.get(key)
            if old_scope:
                conns = self._user_connections.get(old_scope, [])
                self._user_connections[old_scope] = [
                    (b, c) for b, c in conns if (id(b), c) != key
                ]
                if not self._user_connections[old_scope]:
                    del self._user_connections[old_scope]

            # Register new mapping
            self._client_to_user[key] = scope
            if scope not in self._user_connections:
                self._user_connections[scope] = []
            if not any((id(b), c) == key for b, c in self._user_connections[scope]):
                self._user_connections[scope].append((bus, client_id))

    def unregister(self, bus: BusProvider, client_id: Any) -> Optional[int]:
        """Remove a connection. Returns the user_id if found, for cleanup."""
        key = (id(bus), client_id)
        with self._lock:
            scope = self._client_to_user.pop(key, None)
            if scope and scope in self._user_connections:
                self._user_connections[scope] = [
                    (b, c)
                    for b, c in self._user_connections[scope]
                    if (id(b), c) != key
                ]
                # Cleanup empty lists
                if not self._user_connections[scope]:
                    del self._user_connections[scope]
            return scope[0] if scope else None

    def get_connections(
        self, user_id: int, organization_id: Optional[int] = None
    ) -> List[Tuple[BusProvider, Any]]:
        """Get all active connections for a scoped user identity."""
        with self._lock:
            return list(self._user_connections.get(_scope_key(user_id, organization_id), []))

    def is_online(self, user_id: int, organization_id: Optional[int] = None) -> bool:
        """Check if a scoped user identity has at least one active connection."""
        with self._lock:
            return bool(self._user_connections.get(_scope_key(user_id, organization_id)))

    def list_active_users(self) -> list[dict[str, Any]]:
        """Return active user scopes with the current connection count."""
        with self._lock:
            return [
                {
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "connections": len(connections),
                }
                for (user_id, organization_id), connections in self._user_connections.items()
            ]

    def get_user_for_client(self, bus: BusProvider, client_id: Any) -> Optional[int]:
        """Get the user_id associated with a client connection."""
        key = (id(bus), client_id)
        with self._lock:
            scope = self._client_to_user.get(key)
            return scope[0] if scope else None

    def get_scope_for_client(
        self, bus: BusProvider, client_id: Any
    ) -> Optional[Tuple[int, Optional[int]]]:
        """Get the scoped identity associated with a client connection."""
        key = (id(bus), client_id)
        with self._lock:
            scope = self._client_to_user.get(key)
            if not scope:
                return None
            return (scope[0], scope[1])
