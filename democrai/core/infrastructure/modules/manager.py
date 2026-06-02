import asyncio
import os
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType
from typing import Any, Dict, List, Optional
from uuid import uuid4

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.auth.service import validate_module_name
from democrai.core.application.access_policy.manifest import parse_access_manifest_rules
from democrai.core.infrastructure.modules.commands import compute_next_run, invoke_command, lease_heartbeat, refresh_state, start_background_commands, start_managed_command, start_scheduled_command, state_for, track_task
from democrai.core.infrastructure.modules.compat import module_version_match, resolve_module_resource, validate_compatibility
from democrai.core.infrastructure.modules.constants import CURRENT_PLATFORM
from democrai.core.infrastructure.modules.lifecycle import configure_trust, discover_modules, enable_runtime, ensure_started, is_trusted, reload_all_modules, reload_module, schedule_startup, shutdown, start_all_modules, stop_module, try_register_module
from democrai.core.infrastructure.modules.loading import load_modules, load_python_modules, load_sidebar_entries_from_init, normalize_sidebar_entry
from democrai.core.runtime.foundation.registry import ModuleCommandRegistration

@dataclass
class ModuleCommandRunState:
    name: str
    lifecycle: str
    runs: int = 0
    last_started_at: Optional[datetime] = None
    last_finished_at: Optional[datetime] = None
    last_status: str = "idle"
    last_error: Optional[str] = None
    next_run_at: Optional[datetime] = None


class Module:
    def __init__(self, path: str, manifest: dict, is_builtin: bool = True, *, owner_id: str):
        self.path = path
        self.is_builtin = is_builtin
        self.owner_id = owner_id
        self.name = validate_module_name(manifest["name"])
        self.label = manifest["label"]
        self.version = manifest.get("version", "1.0.0")
        self.type = manifest.get("type", "python")
        self.requirements = manifest.get("requirements", {})
        self.platforms = manifest.get("platforms", {})
        self.auth = manifest.get("auth", {})
        self.icon = resolve_module_resource(path, manifest.get("icon", "App"))
        self.sidebar_position = manifest.get("sidebar_position", "top")
        self.authenticated_label = manifest.get("authenticated_label")
        self.authenticated_icon = manifest.get("authenticated_icon")
        self.description = manifest.get("description", "")
        try:
            self.priority = int(manifest.get("priority", 0))
        except (TypeError, ValueError):
            self.priority = 0
        self._manifest = manifest
        subject = AccessSubject.create("module", self.name)
        self.access = (
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="read",
                    target=str(Path(path).expanduser().resolve()),
                ),
            ),
            *parse_access_manifest_rules(
                manifest,
                subject_type="module",
                subject_name=self.name,
            ),
        )
        self.allowed_imports = manifest["allowed_imports"]
        self.sidebar_entries: List[dict[str, Any]] = []
        self.sidebar_init_declared = False
        self.ui_module: Optional[ModuleType] = None
        self.actions_module: Optional[ModuleType] = None
        self.commands_module: Optional[ModuleType] = None
        self._background_tasks: List[asyncio.Task] = []
        self._stop_events: Dict[str, asyncio.Event] = {}
        self._command_states: Dict[str, ModuleCommandRunState] = {}
        self.is_active = False
        self.error_message: Optional[str] = None

    def _version_match(self, current: str, required: str) -> bool:
        return module_version_match(current, required)

    def validate_compatibility(self) -> bool:
        return validate_compatibility(self)

    def load_modules(self, *, load_ui: bool = True):
        return load_modules(self, load_ui=load_ui)

    def _load_python_modules(self, module_rel_path: str, *, load_ui: bool = True):
        return load_python_modules(self, module_rel_path, load_ui=load_ui)

    def _load_sidebar_entries_from_init(self, module_module: ModuleType) -> None:
        return load_sidebar_entries_from_init(self, module_module)

    def _normalize_sidebar_entry(self, raw_entry: Any, *, index: int):
        return normalize_sidebar_entry(self, raw_entry, index=index)

    async def start_background_commands(self):
        return start_background_commands(self)

    def _state_for(self, definition: ModuleCommandRegistration) -> ModuleCommandRunState:
        return state_for(self, definition)

    def _refresh_state(self, definition: ModuleCommandRegistration) -> ModuleCommandRunState:
        return refresh_state(self, definition)

    async def _invoke_command(self, definition: ModuleCommandRegistration, *, stop_event: Optional[asyncio.Event] = None) -> None:
        return await invoke_command(self, definition, stop_event=stop_event)

    def _track_task(self, task: asyncio.Task) -> None:
        return track_task(self, task)

    def _start_managed_command(self, definition: ModuleCommandRegistration, *, restart_on_exit: bool, run_once_after_completion: bool) -> None:
        return start_managed_command(self, definition, restart_on_exit=restart_on_exit, run_once_after_completion=run_once_after_completion)

    def _start_scheduled_command(self, definition: ModuleCommandRegistration) -> None:
        return start_scheduled_command(self, definition)

    def _compute_next_run(self, definition: ModuleCommandRegistration, now: datetime) -> datetime:
        return compute_next_run(self, definition, now)

    async def _lease_heartbeat(self, command_name: str) -> None:
        return await lease_heartbeat(self, command_name)

    def stop(self):
        return stop_module(self)

    def reload(self):
        return reload_module(self)


class ModuleManager:
    def __init__(self):
        self._modules: Dict[str, Module] = {}
        self._background_started = False
        self._start_lock = asyncio.Lock()
        self._start_future = None
        self._owner_id = f"{CURRENT_PLATFORM}:{os.getpid()}:{uuid4().hex[:8]}"
        self._trust_mode = "all"
        self._allow_user_modules = True
        self._trusted_modules: set[str] = set()

    def configure_trust(self, *, trust_mode: str = "all", allow_user_modules: bool = True, trusted_modules: Optional[List[str]] = None) -> None:
        return configure_trust(self, trust_mode=trust_mode, allow_user_modules=allow_user_modules, trusted_modules=trusted_modules)

    def _is_trusted(self, module_name: str, *, is_builtin: bool) -> bool:
        return is_trusted(self, module_name, is_builtin=is_builtin)

    def discover_modules(self, plugins_dir: str, is_builtin: bool = True, *, load_ui: bool = True):
        return discover_modules(self, plugins_dir, is_builtin, load_ui=load_ui)

    def _try_register_module(self, path: str, is_builtin: bool, *, load_ui: bool = True):
        return try_register_module(self, Module, path, is_builtin, load_ui=load_ui)

    def enable_runtime(self):
        return enable_runtime()

    async def start_all_modules(self):
        return await start_all_modules(self)

    async def ensure_started(self):
        return await ensure_started(self)

    def schedule_startup(self, loop: asyncio.AbstractEventLoop | None) -> None:
        return schedule_startup(self, loop)

    def shutdown(self):
        return shutdown(self)

    def get_module(self, name: str) -> Optional[Module]:
        return self._modules.get(name)

    def get_all_modules(self) -> List[Module]:
        return list(self._modules.values())

    def reload_all_modules(self):
        return reload_all_modules(self)


module_manager = ModuleManager()
