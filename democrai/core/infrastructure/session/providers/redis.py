from __future__ import annotations

import json


class RedisJsonStore:
    def __init__(
        self, redis_url: str, prefix: str, ttl_seconds: int | None = None
    ) -> None:
        import redis

        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def load(self, key: str) -> dict[str, object] | None:
        raw = self._redis.get(self._key(key))
        if raw is None:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None

    def save(self, key: str, value: dict[str, object]) -> None:
        payload = json.dumps(value, default=str)
        redis_key = self._key(key)
        if self._ttl_seconds:
            self._redis.setex(redis_key, self._ttl_seconds, payload)
        else:
            self._redis.set(redis_key, payload)

    def delete(self, key: str) -> None:
        self._redis.delete(self._key(key))

    def keys(self) -> list[str]:
        pattern = f"{self._prefix}:*"
        keys = self._redis.keys(pattern)
        prefix_len = len(f"{self._prefix}:")
        return [str(key)[prefix_len:] for key in keys]
