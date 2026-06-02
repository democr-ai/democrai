from __future__ import annotations

from typing import Iterable

ROLE_SUPER = "super"
ROLE_ORGANIZATION = "organization"
ROLE_USER = "user"
ROLE_GUEST = "guest"

# Access level semantics (main user scopes)
# 1 = full visibility
# 2 = organization visibility
# 3 = user visibility
ROLE_LEVEL_SUPER = 1
ROLE_LEVEL_ORGANIZATION = 2
ROLE_LEVEL_USER = 3
ROLE_LEVEL_GUEST = 99

# Named constants for explicit access-level intent
ACCESS_LEVEL_FULL = ROLE_LEVEL_SUPER
ACCESS_LEVEL_ORGANIZATION = ROLE_LEVEL_ORGANIZATION
ACCESS_LEVEL_USER = ROLE_LEVEL_USER

_ROLE_ALIASES = {
    "admin": ROLE_SUPER,
    "super": ROLE_SUPER,
    "organization": ROLE_ORGANIZATION,
    "org": ROLE_ORGANIZATION,
    "user": ROLE_USER,
    "guest": ROLE_GUEST,
}

_ROLE_LEVELS = {
    ROLE_SUPER: ROLE_LEVEL_SUPER,
    ROLE_ORGANIZATION: ROLE_LEVEL_ORGANIZATION,
    ROLE_USER: ROLE_LEVEL_USER,
    ROLE_GUEST: ROLE_LEVEL_GUEST,
}


def normalize_role(role: str | None) -> str:
    if role is None:
        return ROLE_GUEST
    return _ROLE_ALIASES.get(role.lower(), ROLE_USER)


def role_level(role: str | None) -> int:
    return _ROLE_LEVELS[normalize_role(role)]


def resolve_primary_role(roles: Iterable[str] | None) -> str:
    best_role = ROLE_GUEST
    best_level = ROLE_LEVEL_GUEST
    for raw_role in roles or ():
        normalized = normalize_role(raw_role)
        normalized_level = _ROLE_LEVELS[normalized]
        if normalized_level < best_level:
            best_role = normalized
            best_level = normalized_level
    return best_role


def is_super_role(role: str | None = None, *, level: int | None = None) -> bool:
    if level is not None:
        return level == ROLE_LEVEL_SUPER
    return normalize_role(role) == ROLE_SUPER


def is_organization_role(role: str | None = None, *, level: int | None = None) -> bool:
    if level is not None:
        return level == ROLE_LEVEL_ORGANIZATION
    return normalize_role(role) == ROLE_ORGANIZATION


def is_user_role(role: str | None = None, *, level: int | None = None) -> bool:
    if level is not None:
        return level == ROLE_LEVEL_USER
    return normalize_role(role) == ROLE_USER
