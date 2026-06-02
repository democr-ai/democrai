"""Visibility helpers shared by canonical storage and derived projections.

The knowledge subsystem supports owner-only items, organization-visible public
items, and globally visible public items. Rather than applying visibility only
at query time, vector and KG projections are materialized into scope-specific
partitions derived by the helpers in this module.
"""

from __future__ import annotations

from democrai.core.application.auth.roles import ROLE_LEVEL_ORGANIZATION
from democrai.core.application.auth.roles import ROLE_LEVEL_SUPER
from democrai.core.application.auth.roles import ROLE_LEVEL_USER

STRICT_USER_KINDS = frozenset(
    {
        "chat_turn",
        "chat_session",
        "agent_message",
        "agent_session",
        "agent_trace",
        "conversation_turn",
    }
)


def is_strict_user_kind(kind: str) -> bool:
    """Return ``True`` for item kinds that must never be public.

    Chat and agent artifacts are kept strictly bound to their owner because
    promoting them to organization/global scopes would risk leaking private
    conversational context.
    """

    return kind in STRICT_USER_KINDS


def normalize_public_flag(*, kind: str, is_public: bool) -> bool:
    """Normalize the requested public flag according to item kind policy."""
    if is_strict_user_kind(kind):
        return False
    return bool(is_public)


def inherited_visibility_scopes(
    *,
    owner_access_level: int | None,
    organization_id: int | None,
    is_public: bool,
    kind: str,
) -> tuple[tuple[int, int | None], ...]:
    """Return synthetic scopes inherited from a public item.

    The returned tuples represent the extra partitions into which the same
    vector/KG projection must be written so later retrieval can remain a simple
    scope lookup.
    """

    if not normalize_public_flag(kind=kind, is_public=is_public):
        return ()
    if owner_access_level == ROLE_LEVEL_USER:
        scopes: list[tuple[int, int | None]] = []
        if organization_id:
            scopes.append(
                (public_organization_scope_id(organization_id), organization_id)
            )
        scopes.append((public_super_scope_id(), None))
        return tuple(scopes)
    if owner_access_level == ROLE_LEVEL_ORGANIZATION:
        return ((public_super_scope_id(), None),)
    return ()


def retrieval_scope_chain(
    *,
    user_id: int,
    organization_id: int | None,
    access_level: int,
) -> tuple[tuple[int, int | None], ...]:
    """Return the ordered set of scopes visible to a requester."""
    scopes: list[tuple[int, int | None]] = [(user_id, organization_id)]
    if access_level <= ROLE_LEVEL_ORGANIZATION and organization_id:
        scopes.append((public_organization_scope_id(organization_id), organization_id))
    if access_level <= ROLE_LEVEL_SUPER:
        scopes.append((public_super_scope_id(), None))
    return tuple(scopes)


def public_organization_scope_id(organization_id: int) -> int:
    """Return the synthetic user identifier representing org-public scope."""
    return -1_000_000_000 - organization_id


def public_super_scope_id() -> int:
    """Return the synthetic user identifier representing globally public scope."""
    return -2_000_000_000
