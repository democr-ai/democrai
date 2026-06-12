from __future__ import annotations

from pathlib import Path
import platform
from datetime import timedelta
from typing import Any

from democrai.core.application.setup.finalization import (
    finalize_setup_runtime,
    publish_setup_finalize_requested,
)
from democrai.core.application.auth.module_access import (
    is_module_locked_for_user,
    module_access_identity,
)
from democrai.core.application.auth.roles import (
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_SUPER,
    ROLE_LEVEL_USER,
)
from democrai.core.application.session_keys import SessionKey
from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    RuntimeNodeRegistry,
    SessionIdentity,
)
from democrai.core.platform.utils.identity import to_optional_int, to_required_int
from democrai.core.platform.utils.timezone import get_system_timezone_name, utc_now_naive
from democrai.core.platform.utils.system import get_resource_monitor
from democrai.core.runtime.bootstrap.config_validation import (
    ConfigValidationResult,
    validate_config_provider,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.exceptions import AccessDeniedError
from democrai.core.runtime.foundation.paths import get_base_dir, get_data_dir
from democrai.core.runtime.observability.profiling import current_request_profiler


def os_name() -> str:
    """Return the normalized current operating system name."""
    return str(platform.system() or "").strip().lower()


def has_nvidia() -> bool:
    """Return whether the current runtime reports an NVIDIA GPU."""
    try:
        resources = get_resource_monitor().get_resources()
    except Exception:
        return False
    return bool(resources.get("has_nvidia_gpu"))


def cuda_toolkit_available() -> bool:
    """Whether the CUDA Toolkit (``nvcc``) is installed for building extensions.

    Distinct from :func:`has_nvidia` (GPU presence) and from the CUDA driver
    version: a GPU/driver can be present without the build toolkit.
    """
    from democrai.core.platform.utils.system import cuda_toolkit_available as _impl

    return _impl()


def can_build_cuda_extension() -> bool:
    """Whether a CUDA source build can succeed here: NVIDIA GPU + CUDA Toolkit.

    Engines should gate CUDA build flags (e.g. ``-DGGML_CUDA=on``) on this rather
    than on GPU presence alone, so a machine with a GPU but no toolkit falls back
    to a working CPU build instead of failing at CMake configuration.
    """
    from democrai.core.platform.utils.system import can_build_cuda_extension as _impl

    return _impl()


def gpu_info() -> dict[str, Any]:
    """Return GPU details reported by the current runtime."""
    try:
        resources = get_resource_monitor().get_resources()
    except Exception:
        return {
            "has_nvidia": False,
            "vram_mb": 0,
            "nvidia_driver_version": "",
            "cuda_driver_version": "",
        }
    return {
        "has_nvidia": bool(resources.get("has_nvidia_gpu")),
        "vram_mb": int(resources.get("vram_total_mb") or 0),
        "nvidia_driver_version": str(resources.get("nvidia_driver_version") or ""),
        "cuda_driver_version": str(resources.get("cuda_driver_version") or ""),
    }


def temp_dir() -> str:
    """Return the application temporary directory under the data directory."""
    path = Path(get_data_dir()) / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


class Modules:
    """Expose read-only metadata about installed and active modules."""

    def __init__(self, sdk) -> None:
        """Create the modules facade for the current SDK instance."""
        self.sdk = sdk

    def list(self) -> list[dict[str, Any]]:
        """Return metadata for all installed modules."""
        module_manager = getattr(app_ctx(), "modules", None)
        if module_manager is None:
            return []
        modules = module_manager.get_all_modules()
        ordered = sorted(
            modules,
            key=lambda item: (str(getattr(item, "label", "") or "").lower(), item.name),
        )
        return [
            {
                "module_name": str(module.name),
                "label": str(getattr(module, "label", module.name) or module.name),
                "version": str(getattr(module, "version", "") or ""),
                "icon": str(getattr(module, "icon", "") or ""),
                "description": str(getattr(module, "description", "") or ""),
            }
            for module in ordered
        ]

    def list_active_for_user(self, user_id: int | None = None) -> list[dict[str, Any]]:
        """Return modules that are not explicitly locked for the user."""
        identity = module_access_identity(self.sdk.session, user_id=user_id)

        return [
            module
            for module in self.list()
            if not is_module_locked_for_user(
                str(module.get("module_name") or "").strip(),
                user_id=identity["user_id"],
                organization_id=identity["organization_id"],
                role=identity["role"],
            )
        ]


class Sessions:
    """Expose session-related operational metrics."""

    def count_active(self) -> int:
        """Count currently active sessions, honoring idle TTL when configured."""
        cfg = getattr(app_ctx(), "config", None)
        idle_ttl = None
        if cfg is not None:
            raw_ttl = cfg.get("session.idle_ttl_seconds")
            try:
                idle_ttl = int(raw_ttl) if raw_ttl not in (None, "", 0, "0") else None
            except Exception:
                idle_ttl = None

        with SessionLocal() as session:
            query = session.query(SessionIdentity)
            if idle_ttl and idle_ttl > 0:
                threshold = utc_now_naive() - timedelta(seconds=idle_ttl)
                query = query.filter(SessionIdentity.updated_at >= threshold)
            return int(query.count())


class Connections:
    """Expose live client connection metrics."""

    def __init__(self, sdk) -> None:
        """Create the connections facade for the current SDK instance."""
        self.sdk = sdk

    def _identity(self) -> tuple[int, int | None, int]:
        user = (self.sdk.session or {}).get(SessionKey.USER) or {}
        return (
            to_optional_int(user.get("id")) or 0,
            to_optional_int(user.get("organization_id")),
            int(user.get("access_level") or ROLE_LEVEL_USER),
        )

    def _visible_rows(self) -> list[dict[str, Any]]:
        registry = getattr(app_ctx(), "connection_registry", None)
        if registry is None:
            return []
        rows = list(registry.list_active_users())
        user_id, organization_id, access_level = self._identity()
        if access_level == ROLE_LEVEL_SUPER:
            return rows
        if access_level == ROLE_LEVEL_ORGANIZATION:
            return [
                row
                for row in rows
                if to_optional_int(row.get("organization_id")) == organization_id
            ]
        return [row for row in rows if to_optional_int(row.get("user_id")) == user_id]

    def list_active_users(self) -> list[dict[str, Any]]:
        """Return live connected user scopes visible to the current session."""
        return self._visible_rows()

    def count_active_users(self) -> int:
        """Count live connected user scopes visible to the current session."""
        return len(self._visible_rows())

    def count_active_connections(self) -> int:
        """Count live client connections visible to the current session."""
        return sum(int(row.get("connections") or 0) for row in self._visible_rows())


class Metrics:
    """Expose lightweight runtime resource metrics."""

    def read(self) -> dict[str, Any]:
        """Return a snapshot of CPU, RAM, and GPU-related metrics."""
        import psutil

        vm = psutil.virtual_memory()
        cpu_percent = float(psutil.cpu_percent(interval=0.0))
        resources = get_resource_monitor().get_resources()
        ram_total_mb = int(resources.get("ram_total_mb") or int(vm.total / (1024 * 1024)))
        ram_free_mb = int(resources.get("ram_free_mb") or int(vm.available / (1024 * 1024)))
        ram_used_mb = max(0, ram_total_mb - ram_free_mb)
        vram_total_mb = int(resources.get("vram_total_mb") or 0)
        vram_free_mb = int(resources.get("vram_free_mb") or 0)
        vram_used_mb = max(0, vram_total_mb - vram_free_mb)

        return {
            "cpu_percent": round(cpu_percent, 1),
            "ram_total_mb": ram_total_mb,
            "ram_free_mb": ram_free_mb,
            "ram_used_mb": ram_used_mb,
            "ram_used_percent": round(float(vm.percent or 0.0), 1),
            "vram_total_mb": vram_total_mb,
            "vram_free_mb": vram_free_mb,
            "vram_used_mb": vram_used_mb,
            "has_nvidia_gpu": bool(resources.get("has_nvidia_gpu")),
        }


class RuntimeNodes:
    """Expose registered runtime nodes for realtime monitor surfaces."""

    def list(self) -> list[dict[str, Any]]:
        """Return runtime nodes registered by the metrics publisher."""
        with SessionLocal() as session:
            rows = (
                session.query(RuntimeNodeRegistry)
                .order_by(RuntimeNodeRegistry.node_id.asc())
                .all()
            )
            return [
                {
                    "id": row.id,
                    "node_id": str(row.node_id or ""),
                    "label": str(row.label or row.node_id or ""),
                    "status": str(row.status or ""),
                    "hostname": str(row.hostname or ""),
                    "has_nvidia_gpu": bool(row.has_nvidia_gpu),
                    "started_at": row.started_at.isoformat() if row.started_at else "",
                    "last_seen_at": (
                        row.last_seen_at.isoformat() if row.last_seen_at else ""
                    ),
                    "updated_at": row.updated_at.isoformat() if row.updated_at else "",
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
                for row in rows
            ]


class Notifications:
    """Expose core notification data to module views."""

    def __init__(self, sdk) -> None:
        self.sdk = sdk

    def list(self) -> list[dict[str, Any]]:
        from democrai.core.application.notifications import list_notifications

        return list_notifications(self.sdk.session)

    def count(self) -> int:
        from democrai.core.application.notifications import pending_notification_count

        return pending_notification_count(self.sdk.session)

    def center_view_path(self) -> str:
        from democrai.core.application.notifications import notification_center_view_path

        return notification_center_view_path()


class Setup:
    """Expose application setup-mode helpers."""

    def is_enabled(self) -> bool:
        """Return whether setup mode is currently enabled."""
        try:
            return bool(getattr(app_ctx(), "setup_mode", False))
        except Exception:
            return False

    def finalize(
        self,
        admin_user: str,
        admin_pass: str,
        *,
        admin_email: str | None = None,
    ) -> None:
        """Finalize setup mode, run migrations, and seed the administrator account."""
        finalize_setup_runtime(
            admin_user=admin_user,
            admin_pass=admin_pass,
            admin_email=admin_email,
        )

    async def request_finalize(
        self,
        admin_user: str,
        admin_pass: str,
        *,
        admin_email: str | None = None,
        stream_id: str | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Queue setup finalization through the core runtime consumer."""
        return await publish_setup_finalize_requested(
            admin_user=admin_user,
            admin_pass=admin_pass,
            admin_email=admin_email,
            stream_id=stream_id,
            session_key=session_key,
        )


class System:
    """Top-level operational system domain exposed through the SDK."""

    def __init__(self, sdk) -> None:
        """Create the system facade and its subdomains."""
        self.sdk = sdk
        self.modules = Modules(sdk)
        self.sessions = Sessions()
        self.connections = Connections(sdk)
        self.metrics = Metrics()
        self.runtime_nodes = RuntimeNodes()
        self.notifications = Notifications(sdk)
        self.setup = Setup()

    def os_name(self) -> str:
        """Return the normalized current operating system name."""
        return os_name()

    def has_nvidia(self) -> bool:
        """Return whether the current runtime reports an NVIDIA GPU."""
        return has_nvidia()

    def gpu_info(self) -> dict[str, Any]:
        """Return GPU details reported by the current runtime."""
        return gpu_info()

    def temp_dir(self) -> str:
        """Return the application temporary directory under the data directory."""
        return temp_dir()

    def is_dev(self) -> bool:
        """Return whether the application is running in development mode."""
        return bool(getattr(app_ctx(), "dev", False))

    def log(self, message: str, level: str = "info") -> None:
        """Write a module-prefixed message through the application logger."""
        prefix = f"[{self.sdk.module_name}]"
        logger = app_ctx().logger
        if not logger:
            return
        getattr(logger, level, logger.info)(f"{prefix} {message}", self.sdk.module_name)
