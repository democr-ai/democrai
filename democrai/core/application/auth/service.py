from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from democrai.core.infrastructure.database.models import (
    AuthLoginRateLimit,
    User,
    Role,
    Permission,
)
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.application.auth.jwt import create_access_token, decode_access_token
from democrai.core.runtime.foundation.app import app_ctx, req_ctx
from democrai.core.application.auth.roles import (
    ROLE_GUEST,
    ROLE_LEVEL_GUEST,
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_SUPER,
    ROLE_LEVEL_USER,
    ROLE_ORGANIZATION,
    ROLE_SUPER,
    ROLE_USER,
    normalize_role,
    resolve_primary_role,
)
from democrai.core.runtime.observability.profiling import current_request_profiler
from democrai.core.platform.utils.identity import to_optional_int, to_required_int
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.platform.utils.timezone import utc_now_naive
import bcrypt

from democrai.core.platform.utils.runtime_names import RUNTIME_NAME_SEGMENT_PATTERN


MODULE_NAME_PATTERN = RUNTIME_NAME_SEGMENT_PATTERN
RESERVED_MODULE_NAMES = {"models"}
CORE_MODULE_ROLES = {
    ROLE_SUPER: ("System Administrator", ROLE_LEVEL_SUPER),
    ROLE_ORGANIZATION: ("Organization User", ROLE_LEVEL_ORGANIZATION),
    ROLE_USER: ("Authenticated User", ROLE_LEVEL_USER),
    ROLE_GUEST: ("Guest User", ROLE_LEVEL_GUEST),
}
_LOGIN_FAILURE_WINDOW_SECONDS = 300.0
_LOGIN_LOCKOUT_SECONDS = 900.0
_LOGIN_MAX_FAILURES = 5
_LOGIN_IP_MAX_FAILURES = 20
_DUMMY_PASSWORD_HASH = "$2a$12$KIo8MTw30r.gDmKPxjGOX.r5Ys6MxBGaXfub9RVrYeNkFiBVLtxr2"


def _normalize_login_key(username: str) -> str:
    return username.strip().casefold() if isinstance(username, str) else ""


def _normalize_ip_key(client_ip: str | None) -> str:
    return client_ip.strip() if isinstance(client_ip, str) else ""


@dataclass(frozen=True)
class _LoginRateLimitPolicy:
    max_failures: int
    window_seconds: int
    lockout_seconds: int


def _config_value(key: str, default: Any) -> Any:
    config = getattr(app_ctx(), "config", None)
    if config is None:
        return default
    return config.get(key, default)


def _config_positive_int(key: str, default: int) -> int:
    try:
        value = int(_config_value(key, default))
    except Exception:
        return default
    return value if value > 0 else default


def _login_rate_limit_enabled() -> bool:
    return normalize_bool(
        _config_value("auth.login_rate_limit.enabled", True),
        default=True,
    )


def _login_rate_limit_policy(bucket_type: str) -> _LoginRateLimitPolicy:
    if bucket_type == "ip":
        return _LoginRateLimitPolicy(
            max_failures=_config_positive_int(
                "auth.login_rate_limit.ip.max_failures",
                _LOGIN_IP_MAX_FAILURES,
            ),
            window_seconds=_config_positive_int(
                "auth.login_rate_limit.ip.window_seconds",
                int(_LOGIN_FAILURE_WINDOW_SECONDS),
            ),
            lockout_seconds=_config_positive_int(
                "auth.login_rate_limit.ip.lockout_seconds",
                int(_LOGIN_LOCKOUT_SECONDS),
            ),
        )
    return _LoginRateLimitPolicy(
        max_failures=_config_positive_int(
            "auth.login_rate_limit.username.max_failures",
            _LOGIN_MAX_FAILURES,
        ),
        window_seconds=_config_positive_int(
            "auth.login_rate_limit.username.window_seconds",
            int(_LOGIN_FAILURE_WINDOW_SECONDS),
        ),
        lockout_seconds=_config_positive_int(
            "auth.login_rate_limit.username.lockout_seconds",
            int(_LOGIN_LOCKOUT_SECONDS),
        ),
    )


def _current_client_ip() -> str | None:
    try:
        current = req_ctx()
    except Exception:
        return None
    return _normalize_ip_key(getattr(current, "client_ip", None)) or None


def _login_rate_limit_buckets(
    username: str,
    client_ip: str | None,
) -> list[tuple[str, str]]:
    buckets = []
    username_key = _normalize_login_key(username)
    if username_key:
        buckets.append(("username", username_key))
    ip_key = _normalize_ip_key(client_ip)
    if ip_key:
        buckets.append(("ip", ip_key))
    return buckets


def _get_rate_limit_bucket(db, bucket_type: str, bucket_value: str):
    return (
        db.query(AuthLoginRateLimit)
        .filter(
            AuthLoginRateLimit.bucket_type == bucket_type,
            AuthLoginRateLimit.bucket_value == bucket_value,
        )
        .with_for_update()
        .first()
    )


def _ensure_rate_limit_bucket(db, bucket_type: str, bucket_value: str):
    bucket = _get_rate_limit_bucket(db, bucket_type, bucket_value)
    if bucket is not None:
        return bucket
    now = utc_now_naive()
    bucket = AuthLoginRateLimit(
        bucket_type=bucket_type,
        bucket_value=bucket_value,
        failures=0,
        created_at=now,
        updated_at=now,
    )
    db.add(bucket)
    db.flush()
    return bucket


def _bucket_is_locked(bucket: AuthLoginRateLimit | None, now) -> bool:
    if bucket is None:
        return False
    locked_until = bucket.locked_until
    return locked_until is not None and locked_until > now


def _bucket_within_window(bucket: AuthLoginRateLimit, policy: _LoginRateLimitPolicy, now) -> bool:
    if bucket.window_started_at is None:
        return False
    return now - bucket.window_started_at <= timedelta(seconds=policy.window_seconds)


def _max_login_rate_limit_window_seconds() -> int:
    username_policy = _login_rate_limit_policy("username")
    ip_policy = _login_rate_limit_policy("ip")
    return max(
        username_policy.window_seconds,
        username_policy.lockout_seconds,
        ip_policy.window_seconds,
        ip_policy.lockout_seconds,
    )


def _prune_expired_login_rate_limits(db, now) -> None:
    cutoff = now - timedelta(seconds=_max_login_rate_limit_window_seconds())
    db.query(AuthLoginRateLimit).filter(
        or_(
            AuthLoginRateLimit.last_failed_at.is_(None),
            AuthLoginRateLimit.last_failed_at < cutoff,
        ),
        or_(
            AuthLoginRateLimit.locked_until.is_(None),
            AuthLoginRateLimit.locked_until <= now,
        ),
    ).delete(synchronize_session=False)


def _check_login_allowed_locked(
    db,
    buckets: list[tuple[str, str]],
    now,
    client_ip: str | None,
) -> bool:
    for bucket_type, bucket_value in buckets:
        bucket = _ensure_rate_limit_bucket(db, bucket_type, bucket_value)
        if _bucket_is_locked(bucket, now):
            _record_auth_event(
                event_type="auth.login.rate_limited",
                subject_user_id=None,
                success=False,
                metadata={
                    "reason": "too_many_attempts",
                    "bucket_type": bucket_type,
                    "client_ip": client_ip,
                },
            )
            return False
    return True


def _record_login_failure_locked(
    db,
    buckets: list[tuple[str, str]],
    now,
) -> None:
    for bucket_type, bucket_value in buckets:
        policy = _login_rate_limit_policy(bucket_type)
        bucket = _ensure_rate_limit_bucket(db, bucket_type, bucket_value)
        if not _bucket_within_window(bucket, policy, now):
            bucket.failures = 0
            bucket.window_started_at = now
            bucket.locked_until = None
        bucket.failures = int(bucket.failures or 0) + 1
        bucket.last_failed_at = now
        bucket.updated_at = now
        if bucket.failures >= policy.max_failures:
            bucket.locked_until = now + timedelta(seconds=policy.lockout_seconds)
            bucket.failures = 0


def is_valid_module_name(module_name: str | None) -> bool:
    return bool(
        module_name
        and MODULE_NAME_PATTERN.fullmatch(module_name)
        and module_name not in RESERVED_MODULE_NAMES
    )


def validate_module_name(module_name: str | None) -> str:
    if not is_valid_module_name(module_name):
        raise ValueError(
            "module name may contain only alphanumeric characters and hyphens, and may not use reserved names"
        )
    return module_name


def qualify_module_permission_name(module_name: str, permission_name: str) -> str:
    module_name = validate_module_name(module_name)
    raw_name = permission_name
    if not raw_name:
        raise ValueError("module permission name cannot be empty")
    return (
        raw_name
        if raw_name.startswith(f"{module_name}.")
        else f"{module_name}.{raw_name}"
    )


def qualify_module_role_name(module_name: str, role_name: str) -> str:
    module_name = validate_module_name(module_name)
    raw_name = role_name
    if not raw_name:
        raise ValueError("module role name cannot be empty")
    normalized_core = normalize_role(raw_name)
    if raw_name.lower() == normalized_core and normalized_core in CORE_MODULE_ROLES:
        return normalized_core
    return (
        raw_name
        if raw_name.startswith(f"{module_name}.")
        else f"{module_name}.{raw_name}"
    )


def _ensure_role(db, role_name: str, description: str | None = None) -> Role:
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        fallback_description = CORE_MODULE_ROLES.get(role_name, ("", ROLE_LEVEL_USER))[
            0
        ]
        role = Role(
            name=role_name, description=description or fallback_description or None
        )
        role.permissions = []
        db.add(role)
    elif description and not role.description:
        role.description = description
    if getattr(role, "permissions", None) is None:
        role.permissions = []
    return role


def _ensure_permission(
    db, permission_name: str, description: str | None = None
) -> Permission:
    permission = db.query(Permission).filter(Permission.name == permission_name).first()
    if permission is None:
        permission = Permission(name=permission_name, description=description)
        permission.roles = []
        db.add(permission)
    elif description and not permission.description:
        permission.description = description
    return permission


def _iter_named_entries(
    entries: Any, *, kind: str
) -> list[tuple[str, str | None, dict[str, Any]]]:
    if not entries:
        return []
    if not isinstance(entries, list):
        raise ValueError(f"module auth '{kind}' must be a list")

    normalized: list[tuple[str, str | None, dict[str, Any]]] = []
    for entry in entries:
        if isinstance(entry, str):
            normalized.append((entry, None, {}))
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"module auth '{kind}' entries must be strings or objects")
        name = entry.get("name")
        if not name:
            raise ValueError(f"module auth '{kind}' entry missing name")
        extra = {
            key: value
            for key, value in entry.items()
            if key not in {"name", "description"}
        }
        normalized.append((name, entry.get("description"), extra))
    return normalized


def sync_module_authorization(
    module_name: str, auth_manifest: dict[str, Any] | None
) -> None:
    """
    Synchronizes module-defined roles and permissions with the core database.

    This function parses the module's authentication manifest and ensures that
    all specified permissions and roles exist in the database, qualifying them
    with the module name to avoid collisions.

    :param module_name: The unique identifier of the module (e.g., 'chat').
    :param auth_manifest: The 'auth' section of the module manifest.
    :raises ValueError: If the module name or manifest structure is invalid.
    """
    module_name = validate_module_name(module_name)
    if not auth_manifest:
        return
    if not isinstance(auth_manifest, dict):
        raise ValueError("module auth manifest must be an object")

    db = SessionLocal()
    try:
        permissions_by_name: dict[str, str | None] = {}
        roles_by_name: dict[str, str | None] = {}
        role_permissions: dict[str, set[str]] = {}

        for raw_name, description, _extra in _iter_named_entries(
            auth_manifest.get("permissions", []),
            kind="permissions",
        ):
            permissions_by_name[
                qualify_module_permission_name(module_name, raw_name)
            ] = description

        for raw_name, description, extra in _iter_named_entries(
            auth_manifest.get("roles", []),
            kind="roles",
        ):
            qualified_role = qualify_module_role_name(module_name, raw_name)
            roles_by_name[qualified_role] = description
            for permission_name in extra.get("permissions", []) or []:
                qualified_permission = qualify_module_permission_name(
                    module_name, permission_name
                )
                role_permissions.setdefault(qualified_role, set()).add(
                    qualified_permission
                )
                permissions_by_name.setdefault(qualified_permission, None)

        if "assignments" in auth_manifest:
            assignments = auth_manifest.get("assignments")
            if not isinstance(assignments, dict):
                raise ValueError("module auth 'assignments' must be an object")
            for raw_role_name, permission_names in assignments.items():
                qualified_role = qualify_module_role_name(
                    module_name, str(raw_role_name)
                )
                if qualified_role not in CORE_MODULE_ROLES:
                    roles_by_name.setdefault(qualified_role, None)
                if not isinstance(permission_names, list):
                    raise ValueError(
                        "module auth assignment permissions must be a list"
                    )
                for permission_name in permission_names:
                    qualified_permission = qualify_module_permission_name(
                        module_name,
                        permission_name,
                    )
                    role_permissions.setdefault(qualified_role, set()).add(
                        qualified_permission
                    )
                    permissions_by_name.setdefault(qualified_permission, None)

        persisted_permissions = {
            name: _ensure_permission(db, name, description)
            for name, description in permissions_by_name.items()
        }
        persisted_roles = {
            name: _ensure_role(db, name, description)
            for name, description in roles_by_name.items()
        }
        for role_name in role_permissions:
            if role_name not in persisted_roles:
                persisted_roles[role_name] = _ensure_role(db, role_name)

        for role_name, permission_names in role_permissions.items():
            role = persisted_roles[role_name]
            existing_permission_names = {perm.name for perm in role.permissions}
            for permission_name in permission_names:
                if permission_name not in existing_permission_names:
                    role.permissions.append(persisted_permissions[permission_name])

        db.commit()
        app_ctx().logger.info(
            f"[Auth] Synced module RBAC for '{module_name}' "
            f"({len(persisted_roles)} roles, {len(persisted_permissions)} permissions)."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _record_auth_event(
    *,
    event_type: str,
    subject_user_id: int | None = None,
    success: bool = True,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        from democrai.core.application.observability.service import (
            observability_service,
        )

        observability_service.record_auth_event(
            event_type=event_type,
            subject_user_id=subject_user_id,
            success=success,
            metadata=metadata,
        )
    except Exception:
        return


def check_login_allowed(username: str, client_ip: str | None = None) -> bool:
    if not _login_rate_limit_enabled():
        return True
    buckets = _login_rate_limit_buckets(username, client_ip)
    if not buckets:
        return True
    now = utc_now_naive()
    db = SessionLocal()
    try:
        _prune_expired_login_rate_limits(db, now)
        for bucket_type, bucket_value in buckets:
            bucket = _get_rate_limit_bucket(db, bucket_type, bucket_value)
            if _bucket_is_locked(bucket, now):
                _record_auth_event(
                    event_type="auth.login.rate_limited",
                    subject_user_id=None,
                    success=False,
                    metadata={
                        "reason": "too_many_attempts",
                        "bucket_type": bucket_type,
                        "client_ip": client_ip,
                    },
                )
                db.commit()
                return False
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def record_login_failure(username: str, client_ip: str | None = None) -> None:
    if not _login_rate_limit_enabled():
        return
    buckets = _login_rate_limit_buckets(username, client_ip)
    if not buckets:
        return
    for attempt in range(2):
        now = utc_now_naive()
        db = SessionLocal()
        try:
            _prune_expired_login_rate_limits(db, now)
            _record_login_failure_locked(db, buckets, now)
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def clear_login_failures(username: str) -> None:
    key = _normalize_login_key(username)
    if not key:
        return
    db = SessionLocal()
    try:
        bucket = _get_rate_limit_bucket(db, "username", key)
        if bucket is not None:
            db.delete(bucket)
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def build_token_payload(user_info: dict[str, Any]) -> dict[str, Any]:
    role = normalize_role(
        user_info.get("role") or resolve_primary_role(user_info.get("roles"))
    )
    organization_id = user_info.get("organization_id")
    access_level = user_info.get("access_level", ROLE_LEVEL_USER)
    user_id = int(user_info.get("id"))
    if not user_id:
        raise ValueError(f"USER ID required")
    return {
        "sub": str(user_id),
        "user_id": user_id,
        "role": role,
        "access_level": access_level,
        "organization_id": to_optional_int(organization_id),
    }


def get_hashed_password(plain_text_password):
    # Hash a password for the first time
    #   (Using bcrypt, the salt is saved into the hash itself)
    pwd_bytes = (
        plain_text_password.encode("utf-8")
        if isinstance(plain_text_password, str)
        else plain_text_password
    )
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt())


def check_password(plain_text_password, hashed_password):
    # Check hashed password. Using bcrypt, the salt is saved into the hash itself
    pwd_bytes = (
        plain_text_password.encode("utf-8")
        if isinstance(plain_text_password, str)
        else plain_text_password
    )
    hash_bytes = (
        hashed_password.encode("utf-8")
        if isinstance(hashed_password, str)
        else hashed_password
    )
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def seed_admin_user_custom(username, password, email=None):
    """Creates an admin user with custom credentials in Core."""
    _app_ctx = app_ctx()
    resolved_email = email or ""
    db_core = SessionLocal()
    try:
        # 1. Ensure Super role exists in CORE
        admin_role = db_core.query(Role).filter(Role.name == ROLE_SUPER).first()
        if not admin_role:
            _app_ctx.logger.info("[Auth] Creating super role in CORE...")
            admin_role = Role(
                name=ROLE_SUPER,
                description="System Administrator",
            )
            db_core.add(admin_role)
            db_core.commit()
            db_core.refresh(admin_role)

        # 2. Ensure admin user exists in CORE
        admin_user = db_core.query(User).filter(User.username == username).first()
        if not admin_user:
            _app_ctx.logger.info(f"[Auth] Creating admin user '{username}' in CORE...")
            admin_user = User(
                username=username,
                email=resolved_email,
                password_hash=get_hashed_password(password),
                access_level=ROLE_LEVEL_SUPER,
            )
            admin_user.roles.append(admin_role)
            db_core.add(admin_user)
        else:
            admin_user.email = resolved_email
            admin_user.password_hash = get_hashed_password(password)
            admin_user.access_level = ROLE_LEVEL_SUPER

        db_core.commit()
        _app_ctx.logger.info(
            f"[Auth] Admin user '{username}' seeded successfully in CORE."
        )

    except Exception as e:
        import traceback

        _app_ctx.logger.info(
            f"[Auth] Error seeding custom admin: {e}\n{traceback.format_exc()}"
        )
        db_core.rollback()
        raise
    finally:
        db_core.close()


def verify_user(username, password) -> tuple[bool, Optional[User]]:
    """
    Verifies user credentials against the database.

    :param username: The username to check.
    :param password: The plain-text password to verify.
    :return: A tuple of (success_boolean, user_object_if_successful).
    """
    db = SessionLocal()
    profiler = current_request_profiler()
    try:
        if profiler is not None:
            with profiler.span("auth.verify.query_user"):
                user = db.query(User).filter(User.username == username).first()
        else:
            user = db.query(User).filter(User.username == username).first()

        if user:
            if profiler is not None:
                with profiler.span("auth.verify.check_password"):
                    ok = check_password(password, user.password_hash)
            else:
                ok = check_password(password, user.password_hash)
        else:
            if profiler is not None:
                with profiler.span("auth.verify.check_password"):
                    check_password(password, _DUMMY_PASSWORD_HASH)
            else:
                check_password(password, _DUMMY_PASSWORD_HASH)
            ok = False

        if ok:
            return True, user
        return False, None
    except Exception as e:
        app_ctx().logger.error(f"[Auth] Error verifying user {username}: {e}")
        return False, None
    finally:
        db.close()


def get_user_permissions(user_id: int) -> list[str]:
    """
    Retrieves all permission names granted to a specific user.

    Permissions are collected from all roles assigned to the user.

    :param user_id: The unique integer ID of the user.
    :return: A list of unique permission name strings.
    """
    db = SessionLocal()
    profiler = current_request_profiler()
    try:
        if profiler is not None:
            with profiler.span("auth.permissions.query_user"):
                user = db.query(User).filter(User.id == user_id).first()
        else:
            user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return []

        permissions = set()
        if profiler is not None:
            with profiler.span("auth.permissions.collect"):
                for role in user.roles:
                    for perm in role.permissions:
                        permissions.add(perm.name)
        else:
            for role in user.roles:
                for perm in role.permissions:
                    permissions.add(perm.name)
        return list(permissions)
    except Exception as e:
        app_ctx().logger.error(
            f"[Auth] Error getting permissions for user_id={user_id}: {e}"
        )
        return []
    finally:
        db.close()


def get_user_access_profile(user_id: int) -> Optional[dict]:
    """
    Returns a normalized dictionary of access-related data for a user.

    The profile includes username, email, organization, roles, and access level.

    :param user_id: The unique integer ID of the user.
    :return: A dictionary containing user profile data, or None if user not found.
    """
    db = SessionLocal()
    profiler = current_request_profiler()
    try:
        if profiler is not None:
            with profiler.span("auth.profile.query_user"):
                user = db.query(User).filter(User.id == user_id).first()
        else:
            user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        role_name = resolve_primary_role([r.name for r in user.roles])
        profile = {
            "username": user.username,
            "email": user.email,
            "organization_id": user.organization_id,
            "roles": [normalize_role(r.name) for r in user.roles],
            "role": role_name,
            "access_level": user.access_level,
        }
        if user.id is not None:
            profile["id"] = user.id
        return profile
    except Exception as e:
        app_ctx().logger.error(
            f"[Auth] Error getting access profile for user_id={user_id}: {e}"
        )
        return None
    finally:
        db.close()


def get_user_access_profile_by_username(username: str) -> Optional[dict]:
    """Returns normalized access data for a given username."""
    db = SessionLocal()
    profiler = current_request_profiler()
    try:
        if not username:
            return None

        if profiler is not None:
            with profiler.span("auth.profile.query_user"):
                user = db.query(User).filter(User.username == username).first()
        else:
            user = db.query(User).filter(User.username == username).first()
        if not user:
            return None
        return get_user_access_profile(to_required_int(user.id, "user_id"))
    except Exception as e:
        app_ctx().logger.error(
            f"[Auth] Error getting access profile for username={username}: {e}"
        )
        return None
    finally:
        db.close()


def login_user(username: str, password: str) -> dict[str, Any]:
    client_ip = _current_client_ip()
    buckets = _login_rate_limit_buckets(username, client_ip)
    rate_limit_db = None
    if _login_rate_limit_enabled() and buckets:
        rate_limit_db = SessionLocal()
        try:
            now = utc_now_naive()
            _prune_expired_login_rate_limits(rate_limit_db, now)
            if not _check_login_allowed_locked(rate_limit_db, buckets, now, client_ip):
                rate_limit_db.rollback()
                return {
                    "ok": False,
                    "type": "error",
                    "error": "rate_limited",
                    "details": "Too many attempts. Please try again later.",
                }
        except IntegrityError:
            rate_limit_db.rollback()
            rate_limit_db.close()
            return login_user(username, password)
        except Exception:
            rate_limit_db.rollback()
            rate_limit_db.close()
            raise

    try:
        verified, user = verify_user(username, password)
    except Exception:
        if rate_limit_db is not None:
            rate_limit_db.rollback()
            rate_limit_db.close()
        raise
    subject_user_id = user.id if user else None
    if not verified or user is None or subject_user_id is None:
        if rate_limit_db is not None:
            try:
                _record_login_failure_locked(rate_limit_db, buckets, utc_now_naive())
                rate_limit_db.commit()
            except Exception:
                rate_limit_db.rollback()
                rate_limit_db.close()
                raise
            rate_limit_db.close()
        else:
            record_login_failure(username, client_ip)
        _record_auth_event(
            event_type="auth.login.failed",
            subject_user_id=subject_user_id,
            success=False,
            metadata={"reason": "invalid_credentials", "client_ip": client_ip},
        )
        return {
            "ok": False,
            "type": "error",
            "error": "invalid_credentials",
            "details": "Invalid credentials.",
        }
    if rate_limit_db is not None:
        rate_limit_db.rollback()
        rate_limit_db.close()

    user_info = get_user_access_profile(subject_user_id)
    if not user_info:
        _record_auth_event(
            event_type="auth.login.failed",
            subject_user_id=subject_user_id,
            success=False,
            metadata={"reason": "profile_unavailable", "client_ip": client_ip},
        )
        return {
            "ok": False,
            "type": "error",
            "error": "profile_unavailable",
            "details": "Unable to load user profile.",
        }

    try:
        token_payload = build_token_payload(user_info)
        token = create_access_token(token_payload, None)
    except Exception as exc:
        app_ctx().logger.error(
            f"[Auth] Token creation failed for user {subject_user_id}: {exc}"
        )
        _record_auth_event(
            event_type="auth.login.failed",
            subject_user_id=subject_user_id,
            success=False,
            metadata={"reason": "token_creation_error", "client_ip": client_ip},
        )
        return {
            "ok": False,
            "type": "error",
            "error": "token_creation_error",
            "details": "Internal error during login.",
        }

    if not decode_access_token(token, log_expired=True):
        _record_auth_event(
            event_type="auth.login.failed",
            subject_user_id=subject_user_id,
            success=False,
            metadata={"reason": "token_immediately_invalid", "client_ip": client_ip},
        )
        return {
            "ok": False,
            "type": "error",
            "error": "token_immediately_invalid",
            "details": "Token generation failed.",
        }

    clear_login_failures(username)
    _record_auth_event(
        event_type="auth.login.succeeded",
        subject_user_id=subject_user_id,
        success=True,
        metadata={
            "role": token_payload["role"],
            "organization_id": token_payload["organization_id"],
            "access_level": token_payload["access_level"],
            "client_ip": client_ip,
        },
    )
    return {
        "ok": True,
        "token": token,
        "token_payload": token_payload,
        "user_info": user_info,
        "user_id": token_payload["user_id"],
    }


def refresh_session_token(
    *,
    session_user_id: int | None,
    requester_id: int | None,
) -> dict[str, Any]:
    if session_user_id is None:
        _record_auth_event(
            event_type="auth.token.refresh",
            subject_user_id=None,
            success=False,
            metadata={"reason": "unauthenticated"},
        )
        return {
            "ok": False,
            "type": "error",
            "error": "unauthenticated",
            "details": "No authenticated session to refresh.",
        }
    if requester_id is None or requester_id != session_user_id:
        _record_auth_event(
            event_type="auth.token.refresh",
            subject_user_id=session_user_id,
            success=False,
            metadata={"reason": "unauthorized_refresh"},
        )
        return {
            "ok": False,
            "type": "error",
            "error": "unauthorized_refresh",
            "details": "Refresh token is not authorized.",
        }

    user_info = get_user_access_profile(session_user_id)
    if not user_info:
        _record_auth_event(
            event_type="auth.token.refresh",
            subject_user_id=session_user_id,
            success=False,
            metadata={"reason": "user_not_found"},
        )
        return {
            "ok": False,
            "type": "error",
            "error": "user_not_found",
            "details": "User not found for session refresh.",
        }

    try:
        token_payload = build_token_payload(user_info)
        user_id = token_payload["user_id"]
        token = create_access_token(token_payload, None)
    except Exception as exc:
        app_ctx().logger.error(
            f"[Auth] Token refresh failed for user {session_user_id}: {exc}"
        )
        _record_auth_event(
            event_type="auth.token.refresh",
            subject_user_id=session_user_id,
            success=False,
            metadata={"reason": "refresh_failed"},
        )
        return {
            "ok": False,
            "type": "error",
            "error": "refresh_failed",
            "details": "Unable to refresh token.",
        }

    _record_auth_event(
        event_type="auth.token.refresh",
        subject_user_id=user_id,
        success=True,
        metadata={
            "role": token_payload["role"],
            "organization_id": token_payload["organization_id"],
            "access_level": token_payload["access_level"],
        },
    )
    return {
        "ok": True,
        "token": token,
        "token_payload": token_payload,
        "user_id": token_payload["user_id"],
    }
