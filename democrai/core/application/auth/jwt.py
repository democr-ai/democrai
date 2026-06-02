import os
import jwt
import datetime
from dataclasses import dataclass
from typing import Optional, Any, Dict
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.platform.utils.debug import debug_auth_flow as _debug_auth_flow
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.app import app_ctx


def _get_secret_key() -> str:
    ctx = app_ctx()
    placeholder = "change-me-with-a-long-random-secret"

    if ctx and ctx.config:
        cfg_secret = str(ctx.config.get("auth.jwt_secret") or "").strip()
        if cfg_secret and cfg_secret != placeholder:
            return cfg_secret

    env_secret = str(os.environ.get("AUTH_SECRET_KEY") or "").strip()
    if env_secret and env_secret != placeholder:
        return env_secret

    raise RuntimeError(
        "auth.jwt_secret is required and cannot use placeholder value; set a real secret in config or AUTH_SECRET_KEY."
    )


AVAIBLE_ALGORITHM = ["HS256", "HS384", "HS512"]
ALGORITMS_LENGTH = {"HS256": 32, "HS384": 48, "HS512": 64}
DEFAULT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TTL_SECONDS = 900
DEFAULT_SERVICE_TTL_SECONDS = 300


@dataclass(frozen=True)
class AccessTokenDecodeResult:
    payload: Optional[Dict[str, Any]] = None
    error: str | None = None


def _get_config_value(key: str, default: Any = None) -> Any:
    ctx = app_ctx()
    if ctx and ctx.config:
        return ctx.config.get(key, default)
    return default


def _get_non_empty_config_string(
    key: str, default: Optional[str] = None
) -> Optional[str]:
    configured = _get_config_value(key, default)
    if configured in (None, ""):
        return default
    value = str(configured).strip()
    return value or default


def auth_cookie_name() -> str:
    return _get_non_empty_config_string("auth.cookie_name", "session") or "session"


def auth_cookie_secure() -> bool:
    return normalize_bool(_get_config_value("auth.cookie_secure", False), default=False)


def auth_cookie_http_only() -> bool:
    return normalize_bool(
        _get_config_value("auth.cookie_http_only", True), default=True
    )


def auth_cookie_samesite() -> str:
    configured = str(_get_config_value("auth.cookie_samesite", "lax")).strip().lower()
    if configured in {"lax", "strict", "none"}:
        return configured
    return "lax"


def auth_cookie_domain() -> Optional[str]:
    return _get_non_empty_config_string("auth.cookie_domain")


def session_cookie_name() -> str:
    return (
        _get_non_empty_config_string("session.cookie_name", "democrai_sid")
        or "democrai_sid"
    )


def jwt_issuer() -> str:
    return _get_non_empty_config_string("auth.jwt_issuer", SERVER_NAME) or SERVER_NAME


def jwt_audience() -> Optional[str]:
    return _get_non_empty_config_string("auth.jwt_audience")


def jwt_tid() -> Optional[str]:
    return _get_non_empty_config_string("auth.jwt_tid")


def jwt_access_ttl_seconds() -> int:
    raw = _get_config_value("auth.jwt_access_ttl_seconds", DEFAULT_ACCESS_TTL_SECONDS)
    try:
        parsed = int(raw)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError) as exc:
        app_ctx().logger.warning(
            f"[Auth] Invalid auth.jwt_access_ttl_seconds={raw!r}; using default {DEFAULT_ACCESS_TTL_SECONDS}: {exc}"
        )
        return DEFAULT_ACCESS_TTL_SECONDS
    app_ctx().logger.warning(
        f"[Auth] Invalid auth.jwt_access_ttl_seconds={raw!r}; using default {DEFAULT_ACCESS_TTL_SECONDS}: value must be > 0"
    )
    return DEFAULT_ACCESS_TTL_SECONDS


def jwt_internal_service_ttl_seconds() -> int:
    raw = _get_config_value(
        "auth.jwt_internal_service_ttl_seconds",
        DEFAULT_SERVICE_TTL_SECONDS,
    )
    try:
        parsed = int(raw)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError) as exc:
        app_ctx().logger.warning(
            f"[Auth] Invalid auth.jwt_internal_service_ttl_seconds={raw!r}; using default {DEFAULT_SERVICE_TTL_SECONDS}: {exc}"
        )
        return DEFAULT_SERVICE_TTL_SECONDS
    app_ctx().logger.warning(
        f"[Auth] Invalid auth.jwt_internal_service_ttl_seconds={raw!r}; using default {DEFAULT_SERVICE_TTL_SECONDS}: value must be > 0"
    )
    return DEFAULT_SERVICE_TTL_SECONDS


def _jwt_algorithm() -> str:
    configured_algorithm = str(
        _get_config_value("auth.jwt_algorithm", DEFAULT_ALGORITHM) or ""
    ).strip()
    if configured_algorithm not in AVAIBLE_ALGORITHM:
        return DEFAULT_ALGORITHM
    return configured_algorithm


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    now = datetime.datetime.now(datetime.UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + datetime.timedelta(seconds=jwt_access_ttl_seconds())

    to_encode.update({"exp": expire, "iat": now})
    to_encode.setdefault("iss", jwt_issuer())
    audience = jwt_audience()
    if audience:
        to_encode.setdefault("aud", audience)
    tid = jwt_tid()
    if tid:
        to_encode.setdefault("tid", tid)
    encoded_jwt = jwt.encode(
        to_encode,
        _get_secret_key(),
        algorithm=_jwt_algorithm(),
    )
    _debug_auth_flow(
        "create_access_token",
        user_id=to_encode.get("user_id"),
        sub=to_encode.get("sub"),
        exp=expire.isoformat(),
        iat=now.isoformat(),
        iss=to_encode.get("iss"),
        aud=to_encode.get("aud"),
        tid=to_encode.get("tid"),
    )
    return encoded_jwt


def create_internal_service_token(
    *,
    audience: str,
    scopes: list[str] | tuple[str, ...] | None = None,
    expires_delta: Optional[datetime.timedelta] = None,
) -> str:
    resolved_audience = audience.strip() if isinstance(audience, str) else ""
    if not resolved_audience:
        raise ValueError("audience is required")
    now = datetime.datetime.now(datetime.UTC)
    expire = (
        now + expires_delta
        if expires_delta is not None
        else now + datetime.timedelta(seconds=jwt_internal_service_ttl_seconds())
    )
    ctx = app_ctx()
    payload = {
        "typ": "service",
        "token_type": "service",
        "sub": "service:core-runtime",
        "iss": jwt_issuer(),
        "aud": resolved_audience,
        "iat": now,
        "exp": expire,
        "node_id": ctx.node_id or SERVER_NAME,
        "scopes": scopes or [],
    }
    tid = jwt_tid()
    if tid:
        payload["tid"] = tid
    return jwt.encode(payload, _get_secret_key(), algorithm=_jwt_algorithm())


def decode_internal_service_token(
    token: str,
    *,
    audience: str,
    required_scopes: list[str] | tuple[str, ...] | None = None,
) -> Optional[Dict[str, Any]]:
    resolved_audience = audience.strip() if isinstance(audience, str) else ""
    if not resolved_audience:
        raise ValueError("audience is required")
    try:
        decoded = jwt.decode(
            token,
            _get_secret_key(),
            algorithms=AVAIBLE_ALGORITHM,
            issuer=jwt_issuer(),
            audience=resolved_audience,
            options={"verify_aud": True},
        )
        expected_tid = jwt_tid()
        if expected_tid and decoded.get("tid") != expected_tid:
            raise jwt.PyJWTError("invalid tid")
        if decoded.get("typ") != "service" or decoded.get("token_type") != "service":
            raise jwt.PyJWTError("invalid token type")
        scopes = {scope for scope in list(decoded.get("scopes") or [])}
        missing = [
            scope for scope in list(required_scopes or []) if scope not in scopes
        ]
        if missing:
            raise jwt.PyJWTError("missing scope")
        return decoded
    except jwt.PyJWTError as exc:
        logger = app_ctx().logger
        if logger is not None:
            logger.warning(f"[Auth] Internal service token error: {exc}")
        return None


def decode_access_token(
    token: str,
    *,
    log_expired: bool = True,
) -> Optional[Dict[str, Any]]:
    return decode_access_token_result(token, log_expired=log_expired).payload


def decode_access_token_result(
    token: str,
    *,
    log_expired: bool = True,
) -> AccessTokenDecodeResult:
    _debug_auth_flow(
        "decode_access_token.start",
        token_present=bool(token),
        token_len=len(token) if isinstance(token, str) else 0,
    )
    try:
        issuer = jwt_issuer()
        audience = jwt_audience()
        options = {"verify_aud": audience}
        decoded = jwt.decode(
            token,
            _get_secret_key(),
            algorithms=AVAIBLE_ALGORITHM,
            issuer=issuer,
            audience=audience,
            options=options,
        )
        expected_tid = jwt_tid()
        if expected_tid and decoded.get("tid") != expected_tid:
            raise jwt.PyJWTError("invalid tid")
        _debug_auth_flow(
            "decode_access_token.ok",
            user_id=decoded.get("user_id"),
            sub=decoded.get("sub"),
            exp=decoded.get("exp"),
            iat=decoded.get("iat"),
        )
        return AccessTokenDecodeResult(payload=decoded)
    except jwt.ExpiredSignatureError:
        try:
            unverified = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_exp": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
                algorithms=AVAIBLE_ALGORITHM,
            )
            _debug_auth_flow(
                "decode_access_token.expired",
                exp=unverified.get("exp"),
                iat=unverified.get("iat"),
                now=int(datetime.datetime.now(datetime.UTC).timestamp()),
                user_id=unverified.get("user_id"),
                sub=unverified.get("sub"),
            )
        except Exception:
            _debug_auth_flow("decode_access_token.expired_unverified_decode_failed")
        if log_expired:
            app_ctx().logger.warning("[Auth] Token expired")
        return AccessTokenDecodeResult(error="token_expired")
    except jwt.PyJWTError as e:
        _debug_auth_flow("decode_access_token.error", error=str(e))
        app_ctx().logger.error(f"[Auth] Token error: {e}")
        return AccessTokenDecodeResult(error="invalid_token")
