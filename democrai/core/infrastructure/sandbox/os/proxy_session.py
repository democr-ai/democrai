from __future__ import annotations

from typing import Any

from democrai.core.infrastructure.sandbox.os.models import ApplicationNetworkAllowlist


class ProxySessionManager:
    """Single owner of OS-sandbox CONNECT proxy sessions.

    The hostname-based CONNECT proxy is the primary network enforcement
    mechanism on every platform: the core, engine/extractor workers, installs
    and skill scripts all route their egress through a helper-owned proxy
    session whose allowlist is matched by hostname (CDN/IP-rotation immune).
    This class is the only place that knows the helper start/update/stop
    calls and the proxy environment convention; every call site delegates
    here so allowlist semantics cannot drift between components.
    """

    PROXY_ENV_KEYS = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "WS_PROXY",
        "WSS_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "ws_proxy",
        "wss_proxy",
    )
    NO_PROXY_VALUE = "127.0.0.1,localhost,::1"

    def __init__(self, config: Any | None = None) -> None:
        self._config = config

    def start(self, allowlist: ApplicationNetworkAllowlist) -> dict[str, str]:
        """Start a proxy session via the helper; fail loudly on bad results."""
        from democrai.core.infrastructure.sandbox.os.helper import (
            start_application_network_proxy_session_with_helper,
        )
        from democrai.core.infrastructure.sandbox.process_guard import (
            process_guard_bypass_context,
        )

        with process_guard_bypass_context():
            session = start_application_network_proxy_session_with_helper(
                allowlist,
                config=self._config,
            )
        proxy_url = str(session.get("proxy_url") or "").strip()
        session_id = str(session.get("session_id") or "").strip()
        if not proxy_url or not session_id:
            raise RuntimeError("os_sandbox_proxy_session_invalid")
        return {"session_id": session_id, "proxy_url": proxy_url}

    def update(
        self,
        session_id: str,
        allowlist: ApplicationNetworkAllowlist,
    ) -> None:
        from democrai.core.infrastructure.sandbox.os.helper import (
            update_application_network_proxy_session_with_helper,
        )

        update_application_network_proxy_session_with_helper(
            session_id,
            allowlist,
            config=self._config,
        )

    def stop(self, session_id: str) -> None:
        """Stop a session; best-effort because it runs in cleanup paths."""
        if not session_id:
            return
        from democrai.core.infrastructure.sandbox.os.helper import (
            stop_application_network_proxy_session_with_helper,
        )
        from democrai.core.infrastructure.sandbox.process_guard import (
            process_guard_bypass_context,
        )

        try:
            with process_guard_bypass_context():
                stop_application_network_proxy_session_with_helper(
                    session_id,
                    config=self._config,
                )
        except Exception:
            pass

    def apply_env(self, env: dict[str, str], proxy_url: str) -> None:
        """Point a process environment at the proxy (upper+lower variants)."""
        for key in self.PROXY_ENV_KEYS:
            env[key] = proxy_url
        env["NO_PROXY"] = self.NO_PROXY_VALUE
        env["no_proxy"] = self.NO_PROXY_VALUE

    def start_for_env(
        self,
        allowlist: ApplicationNetworkAllowlist,
        env: dict[str, str],
    ) -> str:
        """Start a session and wire `env` to it; returns the session id."""
        session = self.start(allowlist)
        self.apply_env(env, session["proxy_url"])
        return session["session_id"]
