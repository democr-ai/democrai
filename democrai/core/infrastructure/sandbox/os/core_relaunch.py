from __future__ import annotations

import os
import sys
from dataclasses import replace
from typing import Any

from democrai.core.infrastructure.sandbox.os.allowlist import (
    build_framework_network_allowlist,
)
from democrai.core.infrastructure.sandbox.os.factory import get_core_launch_strategy
from democrai.core.infrastructure.sandbox.os.launch_policy import (
    NETWORK_PROXY,
    NetworkLaunchEndpoint,
    SandboxLaunchPolicy,
    build_launch_policy,
)
from democrai.core.infrastructure.sandbox.os.models import (
    ApplicationNetworkAllowlist,
)


CORE_OS_SANDBOX_REEXEC_ENV = "DEMOCRAI_CORE_OS_SANDBOX_REEXEC"
CORE_OS_SANDBOX_PROXY_SESSION_ENV = "DEMOCRAI_CORE_OS_SANDBOX_PROXY_SESSION_ID"


def is_core_os_sandbox_relaunched() -> bool:
    return str(os.environ.get(CORE_OS_SANDBOX_REEXEC_ENV) or "").strip() == "1"


def provider_supports_current_process_os_sandbox() -> bool:
    return not bool(getattr(get_core_launch_strategy(), "requires_relaunch", False))


def core_os_sandbox_relaunch_required(config: Any) -> bool:
    if not _os_sandbox_enabled(config):
        return False
    return not provider_supports_current_process_os_sandbox()


def ensure_core_os_sandbox_relaunched(args: Any) -> None:
    config = getattr(args, "config", None) or _current_config()
    if not core_os_sandbox_relaunch_required(config):
        return
    if is_core_os_sandbox_relaunched():
        return
    raise RuntimeError("os_sandbox_core_worker_launch_required")


def build_core_worker_launch_policy(
    config: Any,
    *,
    command: list[str],
    env: dict[str, str],
    cwd: str | None,
    runtime_mode: str | None = None,
) -> SandboxLaunchPolicy:
    return _build_core_launch_policy(
        config,
        command=list(command),
        env=dict(env),
        cwd=cwd,
        runtime_mode=runtime_mode,
    )


def update_core_os_sandbox_proxy_session(
    allowlist: ApplicationNetworkAllowlist,
    *,
    config: Any | None = None,
) -> bool:
    session_id = str(os.environ.get(CORE_OS_SANDBOX_PROXY_SESSION_ENV) or "").strip()
    if not session_id:
        return False
    from democrai.core.infrastructure.sandbox.os.proxy_session import (
        ProxySessionManager,
    )

    manager = ProxySessionManager(config)
    try:
        manager.update(session_id, allowlist)
    except RuntimeError as exc:
        if not str(exc).startswith("os_sandbox_proxy_session_not_found:"):
            raise
        if not _core_proxy_session_recovery_allowed():
            raise
        session = _start_core_proxy_session(
            allowlist,
            config=config or _current_config(),
        )
        proxy_url = str(session.get("proxy_url") or "").strip()
        recovered_session_id = str(session.get("session_id") or "").strip()
        if not proxy_url or not recovered_session_id:
            raise RuntimeError("os_sandbox_core_proxy_session_invalid") from exc
        manager.apply_env(os.environ, proxy_url)
        os.environ[CORE_OS_SANDBOX_PROXY_SESSION_ENV] = recovered_session_id
    return True


def _core_proxy_session_recovery_allowed() -> bool:
    # A relaunched macOS/Windows core may have a platform policy that permits
    # only the original loopback proxy port. In-process providers can safely
    # swap the proxy env to a newly created helper session.
    return (
        provider_supports_current_process_os_sandbox()
        and not is_core_os_sandbox_relaunched()
    )


def ensure_in_process_core_proxy_session(config: Any | None = None) -> bool:
    """Route in-process core traffic through the OS sandbox CONNECT proxy.

    On platforms where the OS sandbox is applied in-process (Linux: seccomp +
    landlock + iptables) rather than via relaunch (macOS/Windows), the proxy
    env that ``_build_core_launch_policy`` injects on relaunch is never set, so
    in-process HTTP clients (urllib/requests) connect directly to the resolved
    IP. CDN hosts (HuggingFace via CloudFront) rotate IPs, so the IP never
    matches the allowlist and the connection is denied.

    This starts a CONNECT proxy session via the helper and points this
    process's ``HTTP(S)_PROXY`` env at it, so traffic is allowlisted by
    hostname (rotation-immune). A loopback connection passes both iptables (the
    ``RETURN`` rule on loopback) and the Python policy guard
    (``_configured_loopback_proxy_target_allowed``) unchanged.

    The proxy is the primary enforcement mechanism: with the sandbox enabled a
    failure to establish the session is a hard error, never a silent
    degradation to IP-based allowlisting. Returns True when a session is
    active, False when the sandbox is disabled or this process is covered by a
    relaunch-time session.
    """
    resolved_config = config if config is not None else _current_config()
    if not _os_sandbox_enabled(resolved_config):
        return False
    # macOS/Windows relaunch already set the proxy env in the child process.
    if not provider_supports_current_process_os_sandbox():
        return False
    if is_core_os_sandbox_relaunched():
        return False
    if str(os.environ.get(CORE_OS_SANDBOX_PROXY_SESSION_ENV) or "").strip():
        return True

    from democrai.core.infrastructure.sandbox.os.proxy_session import (
        ProxySessionManager,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    with process_guard_bypass_context():
        _ensure_core_sandbox_helper_ready(resolved_config)
        allowlist = build_framework_network_allowlist(config=resolved_config)
        session = _start_core_proxy_session(allowlist, config=resolved_config)
        proxy_url = str(session.get("proxy_url") or "").strip()
        session_id = str(session.get("session_id") or "").strip()
        if not proxy_url or not session_id:
            raise RuntimeError("os_sandbox_core_proxy_session_invalid")
        ProxySessionManager(resolved_config).apply_env(os.environ, proxy_url)
        os.environ[CORE_OS_SANDBOX_PROXY_SESSION_ENV] = session_id
    return True


def _build_core_launch_policy(
    config: Any,
    *,
    command: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    runtime_mode: str | None = None,
) -> SandboxLaunchPolicy:
    from democrai.core.infrastructure.sandbox import process_guard as process_guard_mod
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    with process_guard_bypass_context():
        _ensure_core_sandbox_helper_ready(config, runtime_mode=runtime_mode)
        launch_env = _with_core_os_sandbox_helper_env(
            dict(os.environ if env is None else env),
            config=config,
        )
        launch_env[CORE_OS_SANDBOX_REEXEC_ENV] = "1"
        allowlist = build_framework_network_allowlist(config=config)
        session = _start_core_proxy_session(allowlist, config=config)
        proxy_url = str(session.get("proxy_url") or "").strip()
        session_id = str(session.get("session_id") or "").strip()
        if not proxy_url or not session_id:
            raise RuntimeError("os_sandbox_core_proxy_session_invalid")
        from democrai.core.infrastructure.sandbox.os.proxy_session import (
            ProxySessionManager,
        )

        ProxySessionManager(config).apply_env(launch_env, proxy_url)
        launch_env[CORE_OS_SANDBOX_PROXY_SESSION_ENV] = session_id
        access = process_guard_mod._merge_access_rules(
            process_guard_mod._runtime_access(),
            _core_media_storage_access(config),
            _core_execute_access(),
        )
        policy = build_launch_policy(
            command=list(command or _core_relaunch_command()),
            cwd=os.getcwd() if cwd is None else cwd,
            env=launch_env,
            state={
                "subject": "core",
                "subject_kind": "core",
                "subject_chain": ({"kind": "core", "name": "core"},),
                "access": access,
            },
        )
        return replace(
            policy,
            network_mode=NETWORK_PROXY,
            network_endpoints=_network_launch_endpoints(allowlist),
            env=dict(launch_env),
        )


def _start_core_proxy_session(
    allowlist: ApplicationNetworkAllowlist,
    *,
    config: Any,
) -> dict[str, str]:
    from democrai.core.infrastructure.sandbox.os.helper import (
        start_application_network_proxy_session_with_helper,
    )

    return start_application_network_proxy_session_with_helper(
        allowlist,
        config=config,
    )


def _ensure_core_sandbox_helper_ready(
    config: Any,
    *,
    runtime_mode: str | None = None,
) -> None:
    from democrai.core.infrastructure.sandbox.os.helper import (
        ensure_os_sandbox_helper_ready,
    )

    ensure_os_sandbox_helper_ready(
        config,
        runtime_mode=runtime_mode,
    )


def _with_core_os_sandbox_helper_env(
    env: dict[str, str],
    *,
    config: Any,
) -> dict[str, str]:
    from democrai.core.infrastructure.sandbox.os import helper as helper_mod

    resolved = dict(env)
    resolved[helper_mod.OS_SANDBOX_HELPER_SOCKET_ENV] = (
        helper_mod.get_os_sandbox_helper_socket_path(config)
    )
    resolved[helper_mod.OS_SANDBOX_POLICY_FILE_ENV] = (
        helper_mod.get_os_sandbox_policy_file_path(config)
    )
    token = helper_mod.get_os_sandbox_helper_token(config)
    if not token:
        raise RuntimeError("os_sandbox_helper_token_missing_after_ready")
    resolved[helper_mod.OS_SANDBOX_HELPER_TOKEN_ENV] = token
    return resolved


def _core_execute_access():
    from democrai.core.application.access_policy import AccessManifestRule
    from democrai.core.application.access_policy import AccessResource
    from democrai.core.application.access_policy import AccessSubject

    executable = str(sys.executable or "").strip()
    if not executable:
        return ()
    return (
        AccessManifestRule(
            subject=AccessSubject.create("core", "core"),
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="execute",
                target=executable,
            ),
        ),
    )


def _core_media_storage_access(config: Any):
    from democrai.core.application.access_policy import AccessManifestRule
    from democrai.core.application.access_policy import AccessResource
    from democrai.core.application.access_policy import AccessSubject

    getter = getattr(config, "get", None)
    if not callable(getter):
        return ()
    try:
        media_type = str(getter("storage.media.type", "local") or "local").strip().lower()
        media_path = str(getter("storage.media.path") or "").strip()
    except Exception:
        return ()
    if media_type != "local" or not media_path:
        return ()
    subject = AccessSubject.create("core", "core")
    return tuple(
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="filesystem",
                operation=operation,
                target=media_path,
            ),
        )
        for operation in ("read", "create", "modify", "delete")
    )


def _network_launch_endpoints(
    allowlist: ApplicationNetworkAllowlist,
) -> tuple[NetworkLaunchEndpoint, ...]:
    endpoints: list[NetworkLaunchEndpoint] = []
    for endpoint in list(getattr(allowlist, "endpoints", []) or []):
        host = str(getattr(endpoint, "host", "") or "").strip()
        port = int(getattr(endpoint, "port", 0) or 0)
        if not host or port <= 0:
            continue
        endpoints.append(
            NetworkLaunchEndpoint(
                operation="connect",
                target=f"{host}:{port}",
            )
        )
    return tuple(endpoints)


def _core_relaunch_command() -> list[str]:
    return [sys.executable, *sys.argv]


def _current_config() -> Any:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        return app_ctx().config
    except Exception:
        return None


def _os_sandbox_enabled(config: Any) -> bool:
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.enabled", False))
