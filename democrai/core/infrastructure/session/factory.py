from __future__ import annotations

from dataclasses import dataclass

from democrai.core.infrastructure.session.providers import (
    JsonStoreProvider,
    MemoryJsonStore,
    RedisJsonStore,
    SqlAlchemyJsonStore,
    SqlUrlJsonStore,
)
from democrai.core.runtime.foundation.app import app_ctx


IDENTITY_KEYS = frozenset({"user"})
CACHE_PREFIX = "_"


@dataclass(frozen=True)
class SessionProviders:
    identity: JsonStoreProvider
    ui_state: JsonStoreProvider
    cache: JsonStoreProvider


class SessionProviderFactory:
    @staticmethod
    def create() -> SessionProviders:
        from democrai.core.infrastructure.database.models import SessionIdentity, SessionUiState

        ctx = app_ctx()
        if getattr(ctx, "setup_mode", False):
            return SessionProviders(
                identity=MemoryJsonStore(),
                ui_state=MemoryJsonStore(),
                cache=MemoryJsonStore(),
            )
        cfg = ctx.config

        identity_provider = "sqlite"
        ui_state_provider = "sqlite"
        cache_provider = "memory"
        redis_url = "redis://localhost:6379/0"
        cache_ttl = 300
        identity_url = None
        ui_state_url = None

        if cfg:
            identity_provider = cfg.get("session.identity.provider", identity_provider)
            ui_state_provider = cfg.get("session.ui_state.provider", ui_state_provider)
            cache_provider = cfg.get("session.cache.provider", cache_provider)
            session_redis_url = cfg.get("session.redis.url")
            network_redis_url = cfg.get("network.redis.url")
            if session_redis_url is not None:
                redis_url = session_redis_url
            elif network_redis_url is not None:
                redis_url = network_redis_url
            cache_ttl = int(cfg.get("session.cache.ttl_seconds", cache_ttl))
            identity_url = cfg.get("session.identity.url")
            ui_state_url = cfg.get("session.ui_state.url")

        identity = SessionProviderFactory._build_provider(
            identity_provider,
            sqlite_model=SessionIdentity,
            sql_url=identity_url,
            redis_url=redis_url,
            redis_prefix="session:identity",
        )
        ui_state = SessionProviderFactory._build_provider(
            ui_state_provider,
            sqlite_model=SessionUiState,
            sql_url=ui_state_url,
            redis_url=redis_url,
            redis_prefix="session:ui",
        )
        cache = SessionProviderFactory._build_provider(
            cache_provider,
            sqlite_model=None,
            sql_url=None,
            redis_url=redis_url,
            redis_prefix="session:cache",
            ttl_seconds=cache_ttl,
        )
        return SessionProviders(identity=identity, ui_state=ui_state, cache=cache)

    @staticmethod
    def _build_provider(
        provider_name: str,
        *,
        sqlite_model: type | None,
        sql_url: str | None,
        redis_url: str,
        redis_prefix: str,
        ttl_seconds: int | None = None,
    ) -> JsonStoreProvider:
        normalized = provider_name.strip().lower()
        if normalized == "sqlite":
            if sqlite_model is None:
                return MemoryJsonStore()
            return SqlAlchemyJsonStore(sqlite_model)
        if normalized == "memory":
            return MemoryJsonStore()
        if normalized == "postgres":
            if not sql_url:
                raise ValueError("Postgres session provider requires a configured URL")
            return SqlUrlJsonStore(sql_url, table_name=redis_prefix.replace(":", "_"))
        if normalized == "redis":
            return RedisJsonStore(redis_url, prefix=redis_prefix, ttl_seconds=ttl_seconds)
        raise ValueError(f"Unsupported session provider: {provider_name}")
