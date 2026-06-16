from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest


RUN_ENV = "DEMOCRAI_RUN_REAL_SANDBOX_TESTS"


pytestmark = [pytest.mark.sudo_sandbox, pytest.mark.linux_only]


def _requires_real_sandbox() -> None:
    if os.environ.get(RUN_ENV) != "1":
        pytest.skip(f"set {RUN_ENV}=1 to run real sudo sandbox diagnostics")
    if os.geteuid() != 0:
        pytest.skip("real sandbox diagnostics require sudo/root")
    if not sys.platform.startswith("linux"):
        pytest.skip("real sandbox diagnostics are Linux-only")


def _python_env(runtime_root: Path) -> dict[str, str]:
    for item in ("data", "config", "cache", "state"):
        (runtime_root / item).mkdir(parents=True, exist_ok=True)
    (runtime_root / "state" / "democrai" / "logs").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    root = str(Path(__file__).resolve().parents[2])
    current = str(env.get("PYTHONPATH") or "")
    env["PYTHONPATH"] = f"{root}{os.pathsep}{current}" if current else root
    env[RUN_ENV] = "1"
    env["XDG_DATA_HOME"] = str(runtime_root / "data")
    env["XDG_CONFIG_HOME"] = str(runtime_root / "config")
    env["XDG_CACHE_HOME"] = str(runtime_root / "cache")
    env["XDG_STATE_HOME"] = str(runtime_root / "state")
    for key in (
        "SUDO_UID",
        "SUDO_GID",
        "PKEXEC_UID",
    ):
        env.pop(key, None)
    return env


def _short_runtime_root(name: str) -> Path:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return Path(tempfile.gettempdir()) / f"dc-sudo-{os.getpid()}-{digest}"


def _write(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _run_case(script: Path, case: str, *, timeout: int = 30) -> dict:
    runtime_root = _short_runtime_root(case)
    runtime_root.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(script), case],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=_python_env(runtime_root),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"case {case} failed rc={completed.returncode}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    last_line = completed.stdout.strip().splitlines()[-1]
    return json.loads(last_line)


@pytest.fixture()
def sandbox_harness(tmp_path: Path) -> Path:
    helper = _write(
        tmp_path / "sandbox_probe_child.py",
        """
        from __future__ import annotations

        import asyncio
        import json
        import os
        import sys


        def _cgroup() -> str:
            return open("/proc/self/cgroup", "r", encoding="utf-8").read()


        if len(sys.argv) > 1 and sys.argv[1] == "mcp":
            raw = sys.stdin.buffer.read()
            _, _, body = raw.partition(b"\\r\\n\\r\\n")
            if not body:
                _, _, body = raw.partition(b"\\n\\n")
            payload = json.loads(body.decode("utf-8"))
            result = {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "content": {
                        "sandboxed": "democrai_os_sandbox_" in _cgroup(),
                        "cgroup": _cgroup(),
                    }
                },
            }
            encoded = json.dumps(result, ensure_ascii=True).encode("utf-8")
            sys.stdout.buffer.write(b"Content-Length: " + str(len(encoded)).encode("ascii") + b"\\r\\n\\r\\n" + encoded)
            sys.stdout.buffer.flush()
            raise SystemExit(0)

        print(json.dumps({"sandboxed": "democrai_os_sandbox_" in _cgroup(), "cgroup": _cgroup()}))
        """,
    )
    return _write(
        tmp_path / "real_sandbox_harness.py",
        f"""
        from __future__ import annotations

        import asyncio
        import http.server
        import json
        import os
        import shutil
        import socket
        import subprocess
        import sys
        import tempfile
        import threading
        import textwrap
        import traceback
        from pathlib import Path
        from types import SimpleNamespace

        CHILD = {str(helper)!r}


        class Config:
            def __init__(self, values=None):
                self.values = dict(values or {{}})

            def get(self, key, default=None):
                return self.values.get(key, default)


        class HarnessLogger:
            def debug(self, *args, **kwargs):
                return None

            def info(self, *args, **kwargs):
                return None

            def warning(self, *args, **kwargs):
                print(*args, file=sys.stderr)

            def error(self, *args, **kwargs):
                print(*args, file=sys.stderr)
                if kwargs.get("exc_info"):
                    exc_info = sys.exc_info()
                    if exc_info[0] is not None:
                        print(
                            "".join(traceback.format_exception(*exc_info)),
                            file=sys.stderr,
                        )


        def result(**payload):
            print(json.dumps(payload, ensure_ascii=True))


        CLEANUP_PATHS = []


        def track_temp_dir(prefix):
            path = Path(tempfile.mkdtemp(prefix=prefix))
            CLEANUP_PATHS.append(path)
            return path


        def cleanup_generated_paths():
            for path in reversed(CLEANUP_PATHS):
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass


        def cgroup_text(pid="self"):
            return Path(f"/proc/{{pid}}/cgroup").read_text(encoding="utf-8")


        def assert_sandboxed(pid="self"):
            text = cgroup_text(pid)
            if "democrai_os_sandbox_" not in text:
                raise AssertionError(f"process {{pid}} escaped OS sandbox: {{text}}")
            return text


        def app_config():
            from democrai.core.runtime.foundation.app import app_ctx

            cfg = Config({{
                "sandbox.os.enabled": True,
                "sandbox.os.refresh_seconds": 0,
            }})
            ctx = app_ctx()
            ctx.config = cfg
            ctx.setup_mode = False
            ctx.runtime_mode = "test"
            ctx.logger = HarnessLogger()
            # Everything originates from a module: skill/MCP/tool guards inherit
            # the owning module's declared access via the module registry, just
            # as production does. Register the real "system" module so
            # OwnerModuleAccess can resolve it instead of failing closed. The
            # ModuleManager singleton exists but is empty by default, so the
            # guard checks for the resolved module, not for a null registry.
            import json as _json
            from democrai.core.infrastructure.modules.manager import (
                Module as _Module,
                ModuleManager as _ModuleManager,
            )

            _mgr = getattr(ctx, "modules", None)
            if _mgr is None:
                _mgr = _ModuleManager()
                ctx.modules = _mgr
            if _mgr.get_module("system") is None:
                _system_path = os.path.join(os.getcwd(), "modules", "system")
                with open(os.path.join(_system_path, "manifest.json")) as _mh:
                    _system_manifest = _json.load(_mh)
                _mgr._modules["system"] = _Module(
                    _system_path,
                    _system_manifest,
                    is_builtin=True,
                    owner_id="harness",
                )
            return cfg


        def rule(subject_kind, subject, resource_type, operation, target):
            from democrai.core.application.access_policy import AccessManifestRule
            from democrai.core.application.access_policy import AccessResource
            from democrai.core.application.access_policy import AccessSubject

            return AccessManifestRule(
                subject=AccessSubject.create(subject_kind, subject),
                resource=AccessResource.create(
                    resource_type=resource_type,
                    operation=operation,
                    target=str(target),
                ),
            )


        def child_rules(subject_kind, subject):
            return [
                rule(subject_kind, subject, "filesystem", "execute", sys.executable),
                rule(subject_kind, subject, "filesystem", "read", CHILD),
            ]


        def make_fake_extensions():
            def generated_module(body):
                lines = textwrap.dedent(body).splitlines()
                while lines and not lines[0].strip():
                    lines.pop(0)
                first = next((line for line in lines if line.strip()), "")
                base = len(first) - len(first.lstrip())
                if base:
                    lines = [
                        line[base:] if line.startswith(" " * base) else line
                        for line in lines
                    ]
                return "\\n".join(lines) + "\\n"

            def ensure_fake_venv_python(env_root):
                bin_dir = env_root / ".venv" / ("Scripts" if os.name == "nt" else "bin")
                bin_dir.mkdir(parents=True, exist_ok=True)
                target = bin_dir / ("python.exe" if os.name == "nt" else "python")
                if target.exists():
                    return
                try:
                    target.symlink_to(sys.executable)
                except Exception:
                    shutil.copyfile(sys.executable, target)
                    target.chmod(0o755)

            root = track_temp_dir("democrai_sandbox_extensions_")
            engine_root = root / "engines"
            extractor_root = root / "extractors"
            engine_pkg = engine_root / "sudo_probe_engine"
            extractor_pkg = extractor_root / "sudo_probe_extractor"
            engine_pkg.mkdir(parents=True)
            extractor_pkg.mkdir(parents=True)
            (engine_root / "__init__.py").write_text("", encoding="utf-8")
            (extractor_root / "__init__.py").write_text("", encoding="utf-8")
            (engine_pkg / "__init__.py").write_text("", encoding="utf-8")
            (extractor_pkg / "__init__.py").write_text("", encoding="utf-8")
            engine_code = textwrap.dedent('''
                import json
                import subprocess
                import sys


                CHILD = __CHILD__


                def _self_cgroup():
                    text = open("/proc/self/cgroup", "r", encoding="utf-8").read()
                    return {{"sandboxed": "democrai_os_sandbox_" in text, "cgroup": text}}


                class SudoProbeEngine:
                    def __init__(self, config):
                        self.config = config

                    @classmethod
                    def _install_local(cls, **_kwargs):
                        completed = subprocess.run(
                            [sys.executable, CHILD],
                            check=True,
                            text=True,
                            capture_output=True,
                        )
                        return {{"self": _self_cgroup(), "child": json.loads(completed.stdout.strip())}}

                    @classmethod
                    def _validate_config_local(cls, **_kwargs):
                        return {{"self": _self_cgroup()}}

                    def probe(self):
                        completed = subprocess.run(
                            [sys.executable, CHILD],
                            check=True,
                            text=True,
                            capture_output=True,
                        )
                        return {{"self": _self_cgroup(), "child": json.loads(completed.stdout.strip())}}

                    def call_mcp_direct(self):
                        import sudo_probe_mcp_bridge

                        content = sudo_probe_mcp_bridge.invoke(CHILD)
                        return {{"self": _self_cgroup(), "mcp": content}}

                    async def generate_stream(self, messages, options):
                        completed = subprocess.run(
                            [sys.executable, CHILD],
                            check=True,
                            text=True,
                            capture_output=True,
                        )
                        yield {{"id": "sudo-stream-1", "self": _self_cgroup(), "child": json.loads(completed.stdout.strip())}}

                    def materialize_media(self, storage_path):
                        import sudo_probe_engine_media_bridge

                        return sudo_probe_engine_media_bridge.materialize(storage_path)
            ''').replace("__CHILD__", repr(CHILD))
            extractor_code = textwrap.dedent('''
                import asyncio
                import json
                import subprocess
                import sys


                CHILD = __CHILD__


                def _self_cgroup():
                    text = open("/proc/self/cgroup", "r", encoding="utf-8").read()
                    return {{"sandboxed": "democrai_os_sandbox_" in text, "cgroup": text}}


                class SudoProbeExtractor:
                    extractor_id = "sudo_probe_extractor"

                    def __init__(self, config=None):
                        self._config = config

                    @classmethod
                    def _install_local(cls, **_kwargs):
                        completed = subprocess.run(
                            [sys.executable, CHILD],
                            check=True,
                            text=True,
                            capture_output=True,
                        )
                        return {{"self": _self_cgroup(), "child": json.loads(completed.stdout.strip())}}

                    @classmethod
                    def _check_ready_local(cls, **_kwargs):
                        return {{"self": _self_cgroup(), "ready": True}}

                    @classmethod
                    def probe_self(cls):
                        return {{"self": _self_cgroup()}}

                    @classmethod
                    def probe_subprocess(cls):
                        completed = subprocess.run(
                            [sys.executable, CHILD],
                            check=True,
                            text=True,
                            capture_output=True,
                        )
                        return {{"self": _self_cgroup(), "child": json.loads(completed.stdout.strip())}}

                    @classmethod
                    async def call_engine_via_sdk(cls):
                        from democrai.sdk.client import active_sdk

                        resolved = await active_sdk.ai.get_provider_by_model_registry_id(1)
                        if resolved.get("status") != "ok":
                            raise RuntimeError(resolved.get("error") or "provider_unavailable")
                        provider = resolved.get("provider")
                        if provider is None:
                            raise RuntimeError("provider_missing")
                        return await provider.generate_completion(messages=[], options={{}})

                    @classmethod
                    def materialize_media(cls, storage_path):
                        import sudo_probe_extractor_media_bridge

                        return sudo_probe_extractor_media_bridge.materialize(storage_path)
            ''').replace("__CHILD__", repr(CHILD))
            engine_media_bridge_code = generated_module('''
                from __future__ import annotations

                import uuid

                from democrai.core.application.ai.engine.runtime.serialization import json_value
                from democrai.core.application.ai.engine.runtime.serialization import python_value
                from democrai.core.runtime.ipc.local_connection import connect_from_env


                def _request(operation, payload):
                    conn = connect_from_env("DEMOCRAI_ENGINE_WORKER_PARENT")
                    request_id = uuid.uuid4().hex
                    try:
                        conn.send(json_value({{
                            "id": request_id,
                            "parent_request": True,
                            "operation": operation,
                            "payload": payload,
                        }}))
                        while True:
                            response = python_value(conn.recv())
                            if str(response.get("id") or "") != request_id:
                                continue
                            if not response.get("ok"):
                                raise RuntimeError(str(response.get("error") or "engine_parent_media_error"))
                            return response.get("result")
                    finally:
                        conn.close()


                def materialize(storage_path):
                    return _request("media.materialize", {{"storage_path": storage_path}})
            ''')
            extractor_media_bridge_code = generated_module('''
                from __future__ import annotations


                def materialize(storage_path):
                    from democrai.core.runtime.foundation.app import app_ctx

                    materialized = app_ctx().media.get_path(storage_path)
                    return {{
                        "path": str(materialized.path),
                        "temporary": bool(materialized.temporary),
                    }}
            ''')
            mcp_bridge_code = generated_module('''
                from __future__ import annotations

                import sys


                def invoke(child):
                    import democrai.core.platform.mcp.runtime as mcp_runtime_mod
                    from democrai.core.platform.mcp.registry import McpServerRecord

                    mcp_runtime_mod.get_server_by_name = lambda name: McpServerRecord(
                        id=1,
                        name=name,
                        transport="direct",
                        endpoint_url="",
                        config={{"command": [sys.executable], "args": [child, "mcp"]}},
                        enabled=True,
                        timeout_ms=5000,
                    )
                    return mcp_runtime_mod.McpRuntime().invoke_tool(
                        full_name="mcp.sudo_probe.echo",
                        arguments={{"ping": True}},
                        module_name="system",
                    )
            ''')
            (engine_pkg / "engine.py").write_text(engine_code, encoding="utf-8")
            (extractor_pkg / "extractor.py").write_text(extractor_code, encoding="utf-8")
            from democrai.core.runtime.dependencies.engine_env import get_engine_local_env_path
            from democrai.core.runtime.dependencies.engine_env import (
                get_engine_venv_site_packages_path,
            )
            from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_env_path
            from democrai.core.runtime.dependencies.extractor_env import (
                get_extractor_venv_site_packages_path,
            )

            ensure_fake_venv_python(get_engine_local_env_path("sudo_probe_engine"))
            ensure_fake_venv_python(get_extractor_local_env_path("sudo_probe_extractor"))
            CLEANUP_PATHS.append(get_engine_local_env_path("sudo_probe_engine"))
            CLEANUP_PATHS.append(get_extractor_local_env_path("sudo_probe_extractor"))
            engine_env_pkg = (
                get_engine_venv_site_packages_path("sudo_probe_engine")
                / "sudo_probe_engine"
            )
            extractor_env_pkg = (
                get_extractor_venv_site_packages_path("sudo_probe_extractor")
                / "sudo_probe_extractor"
            )
            engine_env_pkg.mkdir(parents=True, exist_ok=True)
            extractor_env_pkg.mkdir(parents=True, exist_ok=True)
            (engine_env_pkg / "__init__.py").write_text("", encoding="utf-8")
            (extractor_env_pkg / "__init__.py").write_text("", encoding="utf-8")
            (engine_env_pkg / "engine.py").write_text(engine_code, encoding="utf-8")
            (extractor_env_pkg / "extractor.py").write_text(extractor_code, encoding="utf-8")
            engine_env_root = get_engine_venv_site_packages_path("sudo_probe_engine")
            extractor_env_root = get_extractor_venv_site_packages_path("sudo_probe_extractor")
            (engine_env_root / "sudo_probe_engine_media_bridge.py").write_text(
                engine_media_bridge_code,
                encoding="utf-8",
            )
            (extractor_env_root / "sudo_probe_extractor_media_bridge.py").write_text(
                extractor_media_bridge_code,
                encoding="utf-8",
            )
            (engine_env_root / "sudo_probe_mcp_bridge.py").write_text(
                mcp_bridge_code,
                encoding="utf-8",
            )
            access = [
                {{"resource_type": "filesystem", "operation": "execute", "target": sys.executable}},
                {{"resource_type": "filesystem", "operation": "read", "target": CHILD}},
                {{"resource_type": "filesystem", "operation": "read", "target": str(root)}},
                {{"resource_type": "filesystem", "operation": "read", "target": str(engine_root)}},
                {{"resource_type": "filesystem", "operation": "read", "target": str(engine_pkg)}},
                {{"resource_type": "network", "operation": "connect", "target": "https://example.com/*"}},
                {{"resource_type": "network", "operation": "receive", "target": "https://example.com/*"}},
            ]
            (engine_pkg / "manifest.json").write_text(json.dumps({{
                "id": "sudo_probe_engine",
                "name": "sudo probe engine",
                "kind": "llm",
                "entrypoint": "sudo_probe_engine.engine:SudoProbeEngine",
                "install": {{"access": access, "allowed_imports": ["json", "subprocess", "sys"]}},
                "runtime": {{"access": access, "allowed_imports": ["json", "subprocess", "sys"]}},
                "provider": {{
                    "id": "sudo_probe_engine",
                    "label": "sudo probe engine",
                    "kind": "llm",
                    "deployment": "local",
                    "model_source": "provider_api",
                    "runtime_methods": ["probe", "call_mcp_direct", "generate_stream", "materialize_media"],
                    "capabilities": ["chat"],
                }},
            }}), encoding="utf-8")
            (extractor_pkg / "manifest.json").write_text(json.dumps({{
                "manifest_version": "1",
                "id": "sudo_probe_extractor",
                "name": "sudo probe extractor",
                "kind": "extractor",
                "entrypoint": "sudo_probe_extractor.extractor:SudoProbeExtractor",
                "file_extensions": [".sudo"],
                "mime_types": ["text/plain"],
                "install": {{"access": access, "allowed_imports": ["json", "subprocess", "sys"]}},
                "runtime": {{"access": access, "allowed_imports": ["json", "subprocess", "sys"]}},
            }}), encoding="utf-8")

            current = str(os.environ.get("PYTHONPATH") or "")
            python_paths = [str(root), str(engine_root), str(extractor_root)]
            if current:
                python_paths.append(current)
            os.environ["PYTHONPATH"] = (
                os.pathsep.join(python_paths)
            )
            os.environ["DEMOCRAI_ENGINES_PATH"] = str(engine_root)
            os.environ["DEMOCRAI_EXTRACTORS_PATH"] = str(extractor_root)
            for path in reversed(python_paths):
                if path and path not in sys.path:
                    sys.path.insert(0, path)
            from democrai.core.runtime.foundation.app import app_ctx
            from democrai.core.application.ai.engine.manifests import list_engine_manifests
            from democrai.core.application.knowledge.extractor.manifests import list_extractor_manifests

            app_ctx().runtime_engine_paths = (str(engine_root),)
            app_ctx().runtime_extractor_paths = (str(extractor_root),)
            list_engine_manifests.cache_clear()
            list_extractor_manifests.cache_clear()
            return root


        def set_probe_request_context():
            from democrai.core.runtime.foundation.app import RequestContext
            from democrai.core.runtime.foundation.app import app_ctx
            from democrai.core.runtime.foundation.app import set_req_ctx

            return set_req_ctx(
                RequestContext(
                    request_id="sudo-sandbox-test",
                    user=1,
                    role="admin",
                    organization_id=1,
                    access_level=100,
                    channel="ipc",
                    app=app_ctx(),
                    session_key="sudo-sandbox-session",
                    module_name="system",
                    stream_id="sudo-sandbox-stream",
                )
            )


        def reset_probe_request_context(token):
            from democrai.core.runtime.foundation.app import reset_req_ctx

            reset_req_ctx(token)


        def patch_probe_model_orchestrator():
            from democrai.core.application.ai import orchestrator as orchestrator_mod

            previous = orchestrator_mod.model_orchestrator.get_provider_by_model_registry_id

            class _SudoProbeProvider:
                async def generate_completion(self, messages=None, options=None):
                    return {{
                        "status": "ok",
                        "orchestrator_provider": True,
                        "engine": {{
                            "orchestrator_boundary": True,
                            "messages": list(messages or []),
                            "options": dict(options or {{}}),
                        }},
                    }}

            async def _get_provider_by_model_registry_id(
                model_registry_id,
                confirm_swap=False,
                **_kwargs,
            ):
                if int(model_registry_id) != 1:
                    return {{
                        "status": "error",
                        "error": f"model_registry_row_not_found:{{model_registry_id}}",
                    }}
                return {{"status": "ok", "provider": _SudoProbeProvider()}}

            orchestrator_mod.model_orchestrator.get_provider_by_model_registry_id = (
                _get_provider_by_model_registry_id
            )
            return lambda: setattr(
                orchestrator_mod.model_orchestrator,
                "get_provider_by_model_registry_id",
                previous,
            )


        def make_fake_skill():
            root = track_temp_dir("democrai_sandbox_skill_")
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            script = scripts / "probe.py"
            script.write_text(
                textwrap.dedent(
                    '''
                    import json
                    import subprocess
                    import socket
                    import sys

                    print("sudo-skill:before-nested", flush=True)
                    completed = subprocess.run(
                        [sys.executable, "-c", "import json; print(json.dumps(dict(ok=True)))"],
                        check=True,
                        text=True,
                        capture_output=True,
                    )
                    print("sudo-skill:after-nested", flush=True)
                    network_blocked = False
                    try:
                        print("sudo-skill:before-network", flush=True)
                        socket.create_connection(("1.1.1.1", 443), timeout=1.0).close()
                        print("sudo-skill:after-network-open", flush=True)
                    except OSError:
                        network_blocked = True
                        print("sudo-skill:after-network-blocked", flush=True)
                    print(json.dumps(dict(
                        nested_returncode=completed.returncode,
                        network_blocked=network_blocked,
                    )))
                    '''
                ),
                encoding="utf-8",
            )
            from democrai.core.platform.agents.models import SkillDefinition
            from democrai.core.platform.agents.models import SkillMetadata
            from democrai.core.platform.agents.registry import skill_registry

            skill_registry.register(
                SkillDefinition(
                    metadata=SkillMetadata(
                        name="system.sudo_probe_skill",
                        description="sudo sandbox probe skill",
                        title="sudo sandbox probe skill",
                        script_paths=("probe.py",),
                        module_name="system",
                    ),
                    content="sudo sandbox probe skill",
                    root_dir=root,
                )
            )
            return root


        class FakeMediaProvider:
            def __init__(self):
                self.root = track_temp_dir("democrai_sandbox_media_")
                self.source = self.root / "source.bin"
                self.source.write_bytes(b"sudo sandbox media")

            def get_path(self, storage_path, destination_dir=None):
                if storage_path != "probe://media":
                    raise FileNotFoundError(storage_path)
                destination = Path(destination_dir) if destination_dir else self.root
                destination.mkdir(parents=True, exist_ok=True)
                target = destination / "materialized.bin"
                shutil.copyfile(self.source, target)
                return SimpleNamespace(
                    path=str(target),
                    temporary=True,
                    cleanup=lambda: None,
                )

            def save_file(self, storage_path, source_path):
                target = self.root / Path(storage_path).name
                shutil.copyfile(source_path, target)
                return storage_path


        def apply_network_guard():
            app_config()
            from democrai.core.infrastructure.sandbox.os.helper import (
                apply_application_network_allowlist_with_helper,
                clear_application_network_allowlist_with_helper,
                ensure_os_sandbox_helper_ready,
            )
            from democrai.core.infrastructure.sandbox.os.models import (
                ApplicationNetworkAllowlist,
            )
            from democrai.core.infrastructure.sandbox.os.linux.network import (
                _chain_names,
                _require_command,
            )

            ensure_os_sandbox_helper_ready(app_config())
            clear_application_network_allowlist_with_helper(pid=os.getpid())
            apply_application_network_allowlist_with_helper(
                ApplicationNetworkAllowlist(endpoints=[]),
                pid=os.getpid(),
            )
            text = assert_sandboxed()
            chain_a, chain_b = _chain_names(os.getpid())
            iptables = _require_command("iptables")
            rules = subprocess.run(
                [iptables, "-S"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
            if chain_a not in rules and chain_b not in rules:
                raise AssertionError("network guard chain missing from iptables")
            try:
                socket.create_connection(("1.1.1.1", 443), timeout=1.0).close()
                raise AssertionError("external network was not blocked by OS sandbox")
            except OSError:
                pass
            return text


        def cleanup_network_guard():
            try:
                from democrai.core.infrastructure.sandbox.os.helper import (
                    clear_application_network_allowlist_with_helper,
                )
                clear_application_network_allowlist_with_helper(pid=os.getpid())
            except Exception:
                pass


        def case_process_guard():
            app_config()
            from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

            blocked = False
            with process_guard_context(
                subject="sudo.process_guard",
                subject_kind="module",
                access=[],
                allow_subprocess=False,
            ):
                try:
                    subprocess.run([sys.executable, CHILD], check=False)
                except (PermissionError, RuntimeError) as exc:
                    blocked = isinstance(exc, PermissionError) or (
                        str(exc) == "sandbox_external_access_check_failed"
                    )
            if not blocked:
                raise AssertionError("process_guard did not block unapproved subprocess")
            result(ok=True, blocked=blocked)


        def case_network_and_subprocess_inheritance():
            try:
                apply_network_guard()
                completed = subprocess.run(
                    [sys.executable, CHILD],
                    check=True,
                    text=True,
                    capture_output=True,
                )
                child = json.loads(completed.stdout.strip())
                if not child["sandboxed"]:
                    raise AssertionError("plain child process did not inherit OS sandbox cgroup")
                result(ok=True, child=child)
            finally:
                cleanup_network_guard()


        def case_sandboxed_process_cannot_control_helper():
            attacker = track_temp_dir("democrai_helper_attack_") / "helper_attack.py"
            attacker.write_text(
                textwrap.dedent(
                    '''
                    import json
                    import os
                    import socket

                    payload = {{
                        "helper_modified": False,
                        "helper_error": None,
                        "helper_attempts": [],
                        "policy_written": False,
                        "policy_error": None,
                        "network_open": False,
                        "network_error": None,
                        "socket_env_present": bool(os.environ.get("DEMOCRAI_OS_SANDBOX_HELPER_SOCKET")),
                        "policy_env_present": bool(os.environ.get("DEMOCRAI_OS_SANDBOX_POLICY_FILE")),
                    }}

                    try:
                        from democrai.core.infrastructure.sandbox.os.helper import (
                            apply_application_network_allowlist_with_helper,
                            clear_application_network_allowlist_with_helper,
                            start_application_network_proxy_session_with_helper,
                            write_os_sandbox_policy_file,
                        )
                        from democrai.core.infrastructure.sandbox.os.models import (
                            ApplicationNetworkAllowlist,
                            NetworkEndpoint,
                        )

                        try:
                            write_os_sandbox_policy_file(ApplicationNetworkAllowlist(endpoints=[]))
                            payload["policy_written"] = True
                        except Exception as exc:
                            payload["policy_error"] = str(exc)

                        try:
                            clear_application_network_allowlist_with_helper(pid=os.getpid())
                            payload["helper_attempts"].append({{"operation": "clear", "ok": True}})
                            payload["helper_modified"] = True
                        except Exception as exc:
                            payload["helper_attempts"].append({{"operation": "clear", "ok": False, "error": str(exc)}})

                        try:
                            apply_application_network_allowlist_with_helper(
                                ApplicationNetworkAllowlist(
                                    endpoints=[
                                        NetworkEndpoint(
                                            host="1.1.1.1",
                                            port=443,
                                            protocol="tcp",
                                            source="sudo.sandbox_escape_attempt",
                                            purpose="helper-control-attack",
                                        )
                                    ]
                                ),
                                pid=os.getpid(),
                            )
                            payload["helper_attempts"].append({{"operation": "apply", "ok": True}})
                            payload["helper_modified"] = True
                        except Exception as exc:
                            payload["helper_attempts"].append({{"operation": "apply", "ok": False, "error": str(exc)}})

                        try:
                            start_application_network_proxy_session_with_helper(
                                ApplicationNetworkAllowlist(endpoints=[])
                            )
                            payload["helper_attempts"].append({{"operation": "start_proxy_session", "ok": True}})
                            payload["helper_modified"] = True
                        except Exception as exc:
                            payload["helper_attempts"].append({{"operation": "start_proxy_session", "ok": False, "error": str(exc)}})
                    except Exception as exc:
                        payload["helper_error"] = str(exc)

                    try:
                        socket.create_connection(("1.1.1.1", 443), timeout=1.0).close()
                        payload["network_open"] = True
                    except OSError as exc:
                        payload["network_error"] = str(exc)

                    print(json.dumps(payload, ensure_ascii=True))
                    '''
                ),
                encoding="utf-8",
            )
            try:
                apply_network_guard()
                attacker_env = dict(os.environ)
                attacker_env.pop("DEMOCRAI_OS_SANDBOX_HELPER_SOCKET", None)
                attacker_env.pop("DEMOCRAI_OS_SANDBOX_POLICY_FILE", None)
                attacker_env.pop("DEMOCRAI_OS_SANDBOX_HELPER_TOKEN", None)
                completed = subprocess.run(
                    [sys.executable, str(attacker)],
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=10,
                    env=attacker_env,
                )
                payload = json.loads(completed.stdout.strip().splitlines()[-1])
                if payload.get("socket_env_present") or payload.get("policy_env_present"):
                    raise AssertionError(
                        f"sandboxed process received helper control env: {{payload!r}}"
                    )
                if payload.get("policy_written"):
                    raise AssertionError(
                        f"sandboxed process wrote helper policy: {{payload!r}}"
                    )
                if payload.get("policy_error") != "os_sandbox_policy_write_denied":
                    raise AssertionError(
                        f"sandboxed process policy write failed for wrong reason: {{payload!r}}"
                    )
                if payload.get("helper_modified"):
                    raise AssertionError(
                        f"sandboxed process modified helper-controlled network rules: {{payload!r}}"
                    )
                if payload.get("network_open"):
                    raise AssertionError(
                        f"sandboxed process opened direct network after helper attack: {{payload!r}}"
                    )
                result(ok=True, payload=payload)
            finally:
                cleanup_network_guard()


        def case_landlock():
            allowed = Path(tempfile.mkdtemp(prefix="democrai_landlock_allowed_"))
            outside = Path(tempfile.mkdtemp(prefix="democrai_landlock_denied_")) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            allowed_file = allowed / "ok.txt"
            allowed_file.write_text("ok", encoding="utf-8")
            from democrai.core.infrastructure.sandbox.os.linux.landlock import apply_landlock_filesystem_rules

            apply_landlock_filesystem_rules(
                read_only_paths=[str(allowed)],
                read_write_paths=[str(allowed)],
            )
            assert allowed_file.read_text(encoding="utf-8") == "ok"
            denied = False
            try:
                outside.read_text(encoding="utf-8")
            except PermissionError:
                denied = True
            if not denied:
                raise AssertionError("landlock allowed filesystem read outside allowlist")
            result(ok=True, denied=denied)


        def case_application_bootstrap():
            cfg = app_config()
            from democrai.core.infrastructure.sandbox.os.bootstrap import bootstrap_current_process_os_sandbox
            from democrai.core.infrastructure.sandbox.os.state import is_application_network_allowlist_active
            from democrai.core.runtime.foundation.app import app_ctx
            try:
                bootstrap_current_process_os_sandbox(
                    app_ctx(),
                    reason="sudo_real_sandbox_test",
                    mode="test",
                )
                if not is_application_network_allowlist_active():
                    raise AssertionError("application OS allowlist was not marked active")
                text = assert_sandboxed()
                result(ok=True, cgroup=text)
            finally:
                try:
                    from democrai.core.infrastructure.sandbox.os.helper import (
                        clear_application_network_allowlist_with_helper,
                    )
                    clear_application_network_allowlist_with_helper(pid=os.getpid())
                except Exception:
                    pass
                cfg.get("sandbox.os.enabled", False)


        def case_engine_install_runtime_and_call():
            try:
                apply_network_guard()
                make_fake_extensions()
                from democrai.core.application.ai.engine.runtime.methods import invoke_engine_class_method
                from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject

                request_token = set_probe_request_context()
                try:
                    install = invoke_engine_class_method(
                        engine_id="sudo_probe_engine",
                        phase="install",
                        method="_install_local",
                        payload={{}},
                    )
                    validation = invoke_engine_class_method(
                        engine_id="sudo_probe_engine",
                        phase="runtime",
                        method="_validate_config_local",
                        payload={{"config": {{}}}},
                        config={{}},
                    )
                    subject = EngineWorkerSubject(
                        engine_id="sudo_probe_engine",
                        config={{"model": "demo"}},
                    )
                    try:
                        worker_probe = subject.invoke("probe", {{}})
                        worker_pid = subject._process.pid
                        worker_cgroup = assert_sandboxed(worker_pid)
                    finally:
                        subject.close()
                finally:
                    reset_probe_request_context(request_token)
                runtime_self = validation["self"]
                if not runtime_self["sandboxed"]:
                    raise AssertionError("engine runtime class method escaped OS sandbox")
                for label, payload in {{
                    "install_self": install["self"],
                    "install_child": install["child"],
                    "worker_self": worker_probe["self"],
                    "worker_child": worker_probe["child"],
                }}.items():
                    if not payload["sandboxed"]:
                        raise AssertionError(f"engine {{label}} subprocess escaped OS sandbox")
                result(ok=True, install=install, worker=worker_probe, worker_cgroup=worker_cgroup, validation=validation)
            finally:
                cleanup_network_guard()


        def case_engine_stream_runtime():
            try:
                apply_network_guard()
                make_fake_extensions()
                from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject

                request_token = set_probe_request_context()
                try:
                    subject = EngineWorkerSubject(
                        engine_id="sudo_probe_engine",
                        config={{"model": "demo"}},
                    )
                    try:
                        async def _collect():
                            items = []
                            async for item in subject.invoke_stream(
                                "generate_stream",
                                {{"messages": [], "options": {{}}}},
                            ):
                                items.append(item)
                            return items

                        chunks = asyncio.run(_collect())
                        worker_pid = subject._process.pid
                        worker_cgroup = assert_sandboxed(worker_pid)
                    finally:
                        subject.close()
                finally:
                    reset_probe_request_context(request_token)
                if not chunks:
                    raise AssertionError("engine stream produced no chunks")
                first = chunks[0]
                if not isinstance(first, dict):
                    raise AssertionError(f"engine stream chunk invalid: {{first!r}}")
                if not first.get("self", {{}}).get("sandboxed"):
                    raise AssertionError("engine stream worker escaped OS sandbox")
                if not first.get("child", {{}}).get("sandboxed"):
                    raise AssertionError("engine stream child escaped OS sandbox")
                result(ok=True, chunks=chunks, worker_cgroup=worker_cgroup)
            finally:
                cleanup_network_guard()


        def case_extractor_install_runtime_and_call():
            try:
                apply_network_guard()
                make_fake_extensions()
                from democrai.core.application.knowledge.extractor.worker_subject import ExtractorWorkerSubject

                request_token = set_probe_request_context()
                try:
                    for phase in ("install", "runtime"):
                        subject = ExtractorWorkerSubject(
                            extractor_id="sudo_probe_extractor",
                            phase=phase,
                            config={{}},
                        )
                        try:
                            payload = subject.invoke_class(
                                "probe_subprocess",
                                {{}},
                            )
                            worker_pid = subject._process.pid
                            assert_sandboxed(worker_pid)
                        finally:
                            subject.close()
                        for label, value in payload.items():
                            if isinstance(value, dict) and not value.get("sandboxed", True):
                                raise AssertionError(f"extractor {{phase}} {{label}} escaped OS sandbox")
                finally:
                    reset_probe_request_context(request_token)
                result(ok=True)
            finally:
                cleanup_network_guard()


        def case_media_parent_requests():
            try:
                apply_network_guard()
                make_fake_extensions()
                from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject
                from democrai.core.application.knowledge.extractor.worker_subject import ExtractorWorkerSubject
                from democrai.core.runtime.foundation.app import app_ctx

                app_ctx().media = FakeMediaProvider()
                request_token = set_probe_request_context()
                try:
                    engine_subject = EngineWorkerSubject(
                        engine_id="sudo_probe_engine",
                        config={{"model": "demo"}},
                    )
                    try:
                        engine_payload = engine_subject.invoke(
                            "materialize_media",
                            {{"storage_path": "probe://media"}},
                        )
                        engine_cgroup = assert_sandboxed(engine_subject._process.pid)
                    finally:
                        engine_subject.close()

                    extractor_subject = ExtractorWorkerSubject(
                        extractor_id="sudo_probe_extractor",
                        phase="runtime",
                        config={{}},
                    )
                    try:
                        extractor_payload = extractor_subject.invoke_class(
                            "materialize_media",
                            {{"storage_path": "probe://media"}},
                        )
                        extractor_cgroup = assert_sandboxed(extractor_subject._process.pid)
                    finally:
                        extractor_subject.close()
                finally:
                    reset_probe_request_context(request_token)
                for label, payload in {{
                    "engine": engine_payload,
                    "extractor": extractor_payload,
                }}.items():
                    path = Path(str(payload.get("path") or ""))
                    if not path.is_file():
                        raise AssertionError(f"{{label}} media materialization missing: {{payload!r}}")
                    if path.read_bytes() != b"sudo sandbox media":
                        raise AssertionError(f"{{label}} media materialization content mismatch")
                result(
                    ok=True,
                    engine=engine_payload,
                    extractor=extractor_payload,
                    engine_cgroup=engine_cgroup,
                    extractor_cgroup=extractor_cgroup,
                )
            finally:
                cleanup_network_guard()


        def case_extractor_calls_engine_via_sdk():
            try:
                apply_network_guard()
                make_fake_extensions()
                from democrai.core.application.knowledge.extractor.worker_subject import ExtractorWorkerSubject

                restore_model_orchestrator = patch_probe_model_orchestrator()
                request_token = set_probe_request_context()
                try:
                    subject = ExtractorWorkerSubject(
                        extractor_id="sudo_probe_extractor",
                        phase="runtime",
                        config={{}},
                    )
                    try:
                        payload = subject.invoke_class("call_engine_via_sdk", {{}})
                        extractor_worker_pid = subject._process.pid
                        extractor_worker_cgroup = assert_sandboxed(extractor_worker_pid)
                    finally:
                        subject.close()
                finally:
                    reset_probe_request_context(request_token)
                    restore_model_orchestrator()
                engine_payload = payload.get("engine")
                if not isinstance(engine_payload, dict):
                    raise AssertionError("extractor engine payload missing")
                if not payload.get("orchestrator_provider"):
                    raise AssertionError("extractor SDK did not use orchestrator provider")
                if not engine_payload.get("orchestrator_boundary"):
                    raise AssertionError("extractor SDK did not cross orchestrator boundary")
                result(
                    ok=True,
                    extractor_worker_cgroup=extractor_worker_cgroup,
                    engine=payload,
                )
            finally:
                cleanup_network_guard()


        def case_extractor_direct_engine_spawn_blocked():
            try:
                make_fake_extensions()
                extractor_dir = Path(os.environ["DEMOCRAI_EXTRACTORS_PATH"]) / "sudo_probe_extractor"
                (extractor_dir / "forbidden_core_import.py").write_text(
                    "from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject\\n",
                    encoding="utf-8",
                )
                from democrai.core.application.knowledge.extractor.worker_subject import ExtractorWorkerSubject

                blocked = False
                error = ""
                try:
                    subject = ExtractorWorkerSubject(
                        extractor_id="sudo_probe_extractor",
                        phase="runtime",
                        config={{}},
                    )
                    try:
                        subject.invoke_class("probe_self", {{}})
                    finally:
                        subject.close()
                except RuntimeError as exc:
                    error = str(exc)
                    blocked = "extractor_sdk_boundary_violation" in error
                if not blocked:
                    raise AssertionError(
                        f"extractor direct core import was not blocked: {{error}}"
                    )
                result(ok=True, blocked=blocked, error=error.split("\\n", 1)[0])
            finally:
                cleanup_network_guard()


        def case_engine_calls_mcp_direct_command():
            # Upstream of an engine there is always a module (the orchestrator
            # invokes the engine on the module's behalf). The engine worker is
            # isolated and carries no module registry, so it is never the
            # owner that resolves MCP access: the module is. This models that
            # topology — the system module request context drives the engine
            # worker (which runs sandboxed) and owns the MCP direct call, which
            # is issued from the module side and also runs sandboxed.
            try:
                apply_network_guard()
                make_fake_extensions()
                import democrai.core.platform.mcp.runtime as mcp_runtime_mod
                from democrai.core.platform.mcp.registry import McpServerRecord
                from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject

                mcp_runtime_mod.get_server_by_name = lambda name: McpServerRecord(
                    id=1,
                    name=name,
                    transport="direct",
                    endpoint_url="",
                    config={{"command": [sys.executable], "args": [CHILD, "mcp"]}},
                    enabled=True,
                    timeout_ms=5000,
                )
                request_token = set_probe_request_context()
                try:
                    subject = EngineWorkerSubject(
                        engine_id="sudo_probe_engine",
                        config={{"model": "demo"}},
                    )
                    try:
                        worker_probe = subject.invoke("probe", {{}})
                        worker_pid = subject._process.pid
                        worker_cgroup = assert_sandboxed(worker_pid)
                    finally:
                        subject.close()
                    content = mcp_runtime_mod.McpRuntime().invoke_tool(
                        full_name="mcp.sudo_probe.echo",
                        arguments={{"ping": True}},
                        module_name="system",
                    )
                finally:
                    reset_probe_request_context(request_token)
                if not isinstance(worker_probe, dict):
                    raise AssertionError("engine worker payload missing")
                if not worker_probe.get("self", {{}}).get("sandboxed"):
                    raise AssertionError("engine worker escaped OS sandbox")
                if not worker_probe.get("child", {{}}).get("sandboxed"):
                    raise AssertionError("engine worker child escaped OS sandbox")
                if not isinstance(content, dict) or not content.get("sandboxed"):
                    raise AssertionError(f"module mcp direct command escaped OS sandbox: {{content!r}}")
                result(ok=True, worker_cgroup=worker_cgroup, worker=worker_probe, content=content)
            finally:
                cleanup_network_guard()


        def case_pipeline_tool_call_runs_skill_script():
            try:
                apply_network_guard()
                make_fake_skill()
                from democrai.sdk.client import SDK

                SDK("", "core", session={{"user": {{"id": 1, "organization_id": 1}}}})
                from democrai.core.application.ai.engine.pipeline.execution import (
                    generate_completion_pipeline,
                )
                from democrai.core.application.ai.engine.schemas.completion import (
                    CompletionResponse,
                    ToolCall,
                )
                from democrai.core.application.ai.pipeline_context import (
                    ai_pipeline_context,
                    create_ai_pipeline_context,
                )
                from democrai.core.application.observability.service import (
                    observability_service,
                )

                observability_service.record_ai_model_pipeline_step = (
                    lambda **kwargs: {{"id": kwargs["step_id"]}}
                )

                class ToolCallProvider:
                    engine_id = "sudo_probe_engine"
                    config = {{}}

                    def __init__(self):
                        self.calls = 0

                    async def _invoke_with_usage(self, method, payload, metadata=None):
                        self.calls += 1
                        if self.calls == 1:
                            return CompletionResponse(
                                id="sudo-tool-call",
                                content="",
                                tool_calls=[
                                    ToolCall(
                                        id="sudo-call-1",
                                        function_name="core.run-skill-script",
                                        arguments=json.dumps({{
                                            "skill": "system.sudo_probe_skill",
                                            "script": "probe.py",
                                            "timeout_seconds": 10,
                                        }}),
                                    )
                                ],
                            )
                        return CompletionResponse(
                            id="sudo-final",
                            content="tool cycle complete",
                        )

                async def _run():
                    provider = ToolCallProvider()
                    context = create_ai_pipeline_context(
                        root_method="sudo_sandbox_pipeline_tool",
                        request_id="sudo-sandbox-pipeline-tool",
                    )
                    context.selected_skills = ("system.sudo_probe_skill",)
                    with ai_pipeline_context(context):
                        response = await generate_completion_pipeline(
                            provider,
                            messages=[],
                            options={{
                                "skills": ["system.sudo_probe_skill"],
                                "tools": ["core.run-skill-script"],
                                "tool_max_iterations": 1,
                            }},
                        )
                    return provider.calls, response

                request_token = set_probe_request_context()
                try:
                    calls, response = asyncio.run(_run())
                finally:
                    reset_probe_request_context(request_token)
                if calls != 2:
                    raise AssertionError(f"pipeline did not perform tool-call roundtrip: {{calls}}")
                if response.content != "tool cycle complete":
                    raise AssertionError(f"pipeline final response invalid: {{response!r}}")
                result(ok=True, calls=calls, content=response.content)
            finally:
                cleanup_network_guard()


        def case_skill_tool_call_runs_script():
            try:
                apply_network_guard()
                make_fake_skill()
                from democrai.sdk.client import SDK

                SDK("", "core", session={{"user": {{"id": 1, "organization_id": 1}}}})
                from democrai.core.application.ai.pipeline_context import (
                    ai_pipeline_context,
                    create_ai_pipeline_context,
                )
                from democrai.core.platform.agents.tool_runtime import agent_tool_runtime

                async def _run():
                    context = create_ai_pipeline_context(
                        root_method="sudo_sandbox_skill_tool",
                        request_id="sudo-sandbox-skill-tool",
                    )
                    context.selected_skills = ("system.sudo_probe_skill",)
                    with ai_pipeline_context(context):
                        return await agent_tool_runtime.run_tool(
                            "core.run-skill-script",
                            arguments={{
                                "skill": "system.sudo_probe_skill",
                                "script": "probe.py",
                                "timeout_seconds": 10,
                            }},
                            context={{"module_name": "system"}},
                            module_name="system",
                        )

                request_token = set_probe_request_context()
                try:
                    payload = asyncio.run(_run())
                finally:
                    reset_probe_request_context(request_token)
                if not isinstance(payload, dict):
                    raise AssertionError("skill tool payload missing")
                if payload.get("returncode") != 0:
                    raise AssertionError(f"skill script failed: {{payload!r}}")
                stdout = str(payload.get("stdout") or "").strip()
                script_payload = json.loads(stdout.splitlines()[-1])
                if not script_payload.get("network_blocked"):
                    raise AssertionError("skill script external network was not blocked")
                if script_payload.get("nested_returncode") != 0:
                    raise AssertionError("skill script nested subprocess failed")
                result(ok=True, script=script_payload, payload=payload)
            finally:
                cleanup_network_guard()


        def case_mcp_http_registry_endpoint():
            server = None
            try:
                apply_network_guard()
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker

                from democrai.core.infrastructure.database.models import Base
                from democrai.core.infrastructure.database.models import McpServerRegistry
                from democrai.core.runtime.foundation.app import app_ctx

                class Handler(http.server.BaseHTTPRequestHandler):
                    def do_POST(self):
                        length = int(self.headers.get("Content-Length", "0"))
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                        body = json.dumps({{
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "result": {{
                                "content": {{
                                    "ok": True,
                                    "method": payload.get("method"),
                                    "sandboxed": "democrai_os_sandbox_" in cgroup_text(),
                                }}
                            }},
                        }}).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)

                    def log_message(self, format, *args):
                        return

                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = asyncio.to_thread(server.serve_forever)
                db_path = track_temp_dir("democrai_mcp_http_db_") / "mcp.sqlite"
                db_url = f"sqlite:///{{db_path}}"
                app_ctx().config.values["database.url"] = db_url
                engine = create_engine(db_url)
                Base.metadata.create_all(engine)
                with engine.connect() as connection:
                    if not engine.dialect.has_table(
                        connection,
                        "external_access_requests",
                    ):
                        raise AssertionError("external_access_requests table was not created")
                Session = sessionmaker(bind=engine)
                with Session() as session:
                    session.add(
                        McpServerRegistry(
                            name="sudo_http_probe",
                            transport="http",
                            endpoint_url=(
                                f"http://127.0.0.1:{{server.server_port}}/mcp"
                            ),
                            config_encrypted="",
                            enabled=True,
                            timeout_ms=5000,
                        )
                    )
                    session.commit()

                async def _invoke():
                    task = asyncio.create_task(thread)
                    await asyncio.sleep(0)
                    try:
                        from democrai.core.platform.mcp.runtime import McpRuntime

                        return await asyncio.to_thread(
                            McpRuntime().invoke_tool,
                            full_name="mcp.sudo_http_probe.echo",
                            arguments={{"ping": True}},
                            module_name="system",
                        )
                    finally:
                        server.shutdown()
                        await task

                content = asyncio.run(_invoke())
                if not isinstance(content, dict) or not content.get("ok"):
                    raise AssertionError(f"mcp http content invalid: {{content!r}}")
                if not content.get("sandboxed"):
                    raise AssertionError(f"mcp http endpoint escaped OS sandbox: {{content!r}}")
                result(ok=True, content=content)
            finally:
                if server is not None:
                    server.server_close()
                cleanup_network_guard()


        def case_full_boundary_chain():
            server = None
            try:
                apply_network_guard()
                extensions_root = make_fake_extensions()
                make_fake_skill()

                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker

                from democrai.sdk.client import SDK
                from democrai.core.application.ai.engine.pipeline.execution import (
                    generate_completion_pipeline,
                )
                from democrai.core.application.ai.engine.schemas.completion import (
                    CompletionResponse,
                    ToolCall,
                )
                from democrai.core.application.ai.pipeline_context import (
                    ai_pipeline_context,
                    create_ai_pipeline_context,
                )
                from democrai.core.application.observability.service import (
                    observability_service,
                )
                from democrai.core.infrastructure.database.models import Base
                from democrai.core.infrastructure.database.models import McpServerRegistry
                from democrai.core.infrastructure.database.models import Organization
                from democrai.core.infrastructure.database.models import OrganizationMcp
                from democrai.core.platform.agents.models import AgentDefinition
                from democrai.core.platform.agents.registry import agent_registry
                from democrai.core.platform.agents.registry import agent_tool_registry
                from democrai.core.platform.agents.tool_runtime import agent_tool_runtime
                from democrai.core.platform.mcp.registry import McpServerRecord
                from democrai.core.runtime.dependencies.engine_env import (
                    get_engine_local_env_path,
                )
                from democrai.core.runtime.foundation.app import app_ctx

                SDK("", "core", session={{"user": {{"id": 1, "organization_id": 1}}}})

                markers = []
                pipeline_steps = []
                observability_service.record_ai_model_pipeline_step = (
                    lambda **kwargs: pipeline_steps.append(dict(kwargs)) or {{"id": kwargs["step_id"]}}
                )

                class Handler(http.server.BaseHTTPRequestHandler):
                    def do_POST(self):
                        length = int(self.headers.get("Content-Length", "0"))
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                        body = json.dumps({{
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "result": {{
                                "content": {{
                                    "marker": "mcp:http",
                                    "ok": True,
                                    "method": payload.get("method"),
                                    "sandboxed": "democrai_os_sandbox_" in cgroup_text(),
                                }}
                            }},
                        }}).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)

                    def log_message(self, format, *args):
                        return

                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()

                db_path = track_temp_dir("democrai_chain_mcp_db_") / "mcp.sqlite"
                db_url = f"sqlite:///{{db_path}}"
                app_ctx().config.values["database.url"] = db_url
                import democrai.core.infrastructure.database as database_module

                database_module._default_engine = None
                database_module._default_SessionLocal = None
                database_module._db_url = None
                engine = create_engine(db_url)
                Base.metadata.create_all(engine)
                with engine.connect() as connection:
                    if not engine.dialect.has_table(
                        connection,
                        "external_access_requests",
                    ):
                        raise AssertionError("external_access_requests table was not created")
                Session = sessionmaker(bind=engine)
                with Session() as session:
                    session.merge(
                        Organization(
                            id=1,
                            name="sudo sandbox organization",
                        )
                    )
                    mcp_server = McpServerRegistry(
                        name="sudo-chain-http",
                        transport="http",
                        endpoint_url=(
                            f"http://127.0.0.1:{{server.server_port}}/mcp"
                        ),
                        config_encrypted="",
                        enabled=True,
                        timeout_ms=5000,
                    )
                    session.add(mcp_server)
                    session.flush()
                    session.add(
                        OrganizationMcp(
                            organization_id=1,
                            mcp_server_id=mcp_server.id,
                        )
                    )
                    session.commit()

                import democrai.core.platform.mcp.runtime as mcp_runtime_mod

                original_get_server_by_name = mcp_runtime_mod.get_server_by_name

                def get_chain_mcp_server(name):
                    if name == "sudo-chain-direct":
                        return McpServerRecord(
                            id=101,
                            name=name,
                            transport="direct",
                            endpoint_url="",
                            config={{"command": [sys.executable], "args": [CHILD, "mcp"]}},
                            enabled=True,
                            timeout_ms=5000,
                        )
                    return original_get_server_by_name(name)

                mcp_runtime_mod.get_server_by_name = get_chain_mcp_server

                async def http_agent_handler(input="", context=None, agent=None):
                    markers.append("agent:http")
                    payload = await agent_tool_runtime.run_tool(
                        "mcp.sudo-chain-http.echo",
                        arguments={{"marker": "mcp_http"}},
                        module_name="system",
                        context=context,
                    )
                    if not payload.get("sandboxed"):
                        raise AssertionError("chain mcp http endpoint escaped OS sandbox")
                    markers.append("mcp:http")
                    return {{"content": json.dumps(payload, sort_keys=True)}}

                async def direct_agent_handler(input="", context=None, agent=None):
                    markers.append("agent:direct")
                    direct_payload = await agent_tool_runtime.run_tool(
                        "mcp.sudo-chain-direct.echo",
                        arguments={{"marker": "mcp_direct"}},
                        module_name="system",
                        context=context,
                    )
                    if not direct_payload.get("sandboxed"):
                        raise AssertionError("chain mcp direct command escaped OS sandbox")
                    markers.append("mcp:direct")
                    nested_payload = await agent_tool_runtime.run_tool(
                        "agent.system.sudo-chain-http-agent",
                        arguments={{"input": "continue to http mcp"}},
                        context=context,
                    )
                    markers.append("agent:http:return")
                    return {{
                        "content": json.dumps({{
                            "direct": direct_payload,
                            "nested": nested_payload,
                        }}, sort_keys=True)
                    }}

                agent_registry.register(
                    AgentDefinition(
                        name="system.sudo-chain-http-agent",
                        description="sudo chain http agent",
                        objective="chat",
                        handler=http_agent_handler,
                        module_name="system",
                        access=[],
                    )
                )
                agent_registry.register(
                    AgentDefinition(
                        name="system.sudo-chain-agent",
                        description="sudo chain direct agent",
                        objective="chat",
                        handler=direct_agent_handler,
                        module_name="system",
                        access=[],
                    )
                )

                class FirstProvider:
                    engine_id = "sudo_probe_engine"
                    config = {{}}

                    def __init__(self):
                        self.calls = 0

                    async def _invoke_with_usage(self, method, payload, metadata=None):
                        self.calls += 1
                        if self.calls == 1:
                            markers.append("engine:first")
                            return CompletionResponse(
                                id="chain-first-tool",
                                content="",
                                tool_calls=[
                                    ToolCall(
                                        id="chain-call-second-engine",
                                        function_name="system.sudo-chain-second-engine",
                                        arguments=json.dumps({{"input": "run second engine"}}),
                                    )
                                ],
                            )
                        message_dump = json.dumps(
                            [
                                item.model_dump(mode="json", exclude_none=True)
                                if hasattr(item, "model_dump")
                                else item
                                for item in payload.get("messages", [])
                            ],
                            sort_keys=True,
                        )
                        if "error" in message_dump.lower():
                            raise AssertionError(f"first tool call failed: {{message_dump}}")
                        markers.append("engine:first:final")
                        return CompletionResponse(
                            id="chain-first-final",
                            content="full boundary chain complete",
                        )

                class SecondProvider:
                    engine_id = "sudo_probe_engine"
                    config = {{}}

                    def __init__(self):
                        self.calls = 0

                    async def _invoke_with_usage(self, method, payload, metadata=None):
                        self.calls += 1
                        if self.calls == 1:
                            markers.append("engine:second")
                            return CompletionResponse(
                                id="chain-second-skill",
                                content="",
                                tool_calls=[
                                    ToolCall(
                                        id="chain-call-skill",
                                        function_name="core.run-skill-script",
                                        arguments=json.dumps({{
                                            "skill": "system.sudo_probe_skill",
                                            "script": "probe.py",
                                            "timeout_seconds": 10,
                                        }}),
                                    )
                                ],
                            )
                        if self.calls == 2:
                            markers.append("engine:second:agent-tool")
                            return CompletionResponse(
                                id="chain-second-agent",
                                content="",
                                tool_calls=[
                                    ToolCall(
                                        id="chain-call-agent",
                                        function_name="agent.system.sudo-chain-agent",
                                        arguments=json.dumps({{"input": "continue to direct mcp"}}),
                                    )
                                ],
                            )
                        markers.append("engine:second:final")
                        return CompletionResponse(
                            id="chain-second-final",
                            content="second engine complete",
                        )

                    async def generate_completion(self, messages=None, options=None):
                        return await generate_completion_pipeline(
                            self,
                            messages=list(messages or []),
                            options=dict(options or {{}}),
                        )

                async def get_chain_provider_by_model_registry_id(
                    self,
                    model_registry_id,
                    *,
                    confirm_swap=False,
                ):
                    if int(model_registry_id) != 1:
                        return {{"status": "error", "error": "model_not_found"}}
                    return {{"status": "ok", "provider": SecondProvider()}}

                from democrai.sdk.ai import AI

                AI.get_provider_by_model_registry_id = get_chain_provider_by_model_registry_id

                async def chain_second_engine(input="", context=None, sdk=None):
                    markers.append("tool:first")
                    if not context or not context.get("pipeline_id"):
                        raise AssertionError("pipeline context was not propagated to first tool")
                    if sdk is None:
                        raise AssertionError("tool SDK was not provided")
                    resolved = await sdk.ai.get_provider_by_model_registry_id(1)
                    if resolved.get("status") != "ok":
                        raise AssertionError(f"SDK provider resolution failed: {{resolved!r}}")
                    provider = resolved.get("provider")
                    if provider is None:
                        raise AssertionError("SDK provider missing")
                    response = await provider.generate_completion(
                        messages=[],
                        options={{
                            "skills": ["system.sudo_probe_skill"],
                            "tools": ["core.run-skill-script"],
                            "agents": ["system.sudo-chain-agent"],
                            "tool_max_iterations": 4,
                        }},
                    )
                    return {{
                        "response": response.content,
                    }}

                agent_tool_registry.register(
                    "system.sudo-chain-second-engine",
                    chain_second_engine,
                    description="sudo chain second engine tool",
                    input_schema={{"type": "object", "properties": {{"input": {{"type": "string"}}}}}},
                    module_name="system",
                    access=[
                        rule(
                            "tool",
                            "system.sudo-chain-second-engine",
                            "filesystem",
                            "read",
                            extensions_root,
                        ),
                        rule(
                            "tool",
                            "system.sudo-chain-second-engine",
                            "filesystem",
                            "read",
                            extensions_root / "engines",
                        ),
                        rule(
                            "tool",
                            "system.sudo-chain-second-engine",
                            "filesystem",
                            "read",
                            extensions_root / "engines" / "sudo_probe_engine",
                        ),
                        rule(
                            "tool",
                            "system.sudo-chain-second-engine",
                            "filesystem",
                            "read",
                            get_engine_local_env_path("sudo_probe_engine"),
                        ),
                        rule(
                            "tool",
                            "system.sudo-chain-second-engine",
                            "filesystem",
                            "create",
                            get_engine_local_env_path("sudo_probe_engine"),
                        ),
                        rule(
                            "tool",
                            "system.sudo-chain-second-engine",
                            "filesystem",
                            "modify",
                            get_engine_local_env_path("sudo_probe_engine"),
                        ),
                    ],
                )

                async def _run():
                    context = create_ai_pipeline_context(
                        root_method="sudo_sandbox_full_boundary_chain",
                        request_id="sudo-sandbox-full-chain",
                        caller_module="system",
                    )
                    with ai_pipeline_context(context):
                        response = await generate_completion_pipeline(
                            FirstProvider(),
                            messages=[],
                            options={{
                                "tools": ["system.sudo-chain-second-engine"],
                                "tool_max_iterations": 2,
                            }},
                        )
                    return response

                request_token = set_probe_request_context()
                try:
                    response = asyncio.run(_run())
                finally:
                    reset_probe_request_context(request_token)

                expected = [
                    "engine:first",
                    "tool:first",
                    "engine:second",
                    "engine:second:agent-tool",
                    "agent:direct",
                    "mcp:direct",
                    "agent:http",
                    "mcp:http",
                    "agent:http:return",
                    "engine:second:final",
                    "engine:first:final",
                ]
                if markers != expected:
                    raise AssertionError(f"chain markers mismatch: {{markers!r}}")
                step_names = [
                    str(step.get("name") or "")
                    for step in pipeline_steps
                ]
                for required in (
                    "system.sudo-chain-second-engine",
                    "core.run-skill-script",
                    "agent.system.sudo-chain-agent",
                ):
                    if required not in step_names:
                        raise AssertionError(f"pipeline step missing: {{required}} in {{step_names!r}}")
                if response.content != "full boundary chain complete":
                    raise AssertionError(f"chain final response invalid: {{response!r}}")
                result(ok=True, markers=markers, steps=step_names, content=response.content)
            finally:
                try:
                    if server is not None:
                        server.shutdown()
                        server.server_close()
                finally:
                    cleanup_network_guard()


        def case_mcp_direct_command():
            try:
                apply_network_guard()
                import democrai.core.platform.mcp.runtime as mcp_runtime_mod
                from democrai.core.platform.mcp.registry import McpServerRecord

                mcp_runtime_mod.get_server_by_name = lambda name: McpServerRecord(
                    id=1,
                    name=name,
                    transport="direct",
                    endpoint_url="",
                    config={{"command": [sys.executable], "args": [CHILD, "mcp"]}},
                    enabled=True,
                    timeout_ms=5000,
                )
                content = mcp_runtime_mod.McpRuntime().invoke_tool(
                    full_name="mcp.sudo_probe.echo",
                    arguments={{"ping": True}},
                    module_name="system",
                )
                if not isinstance(content, dict) or not content.get("sandboxed"):
                    raise AssertionError(f"mcp direct command escaped OS sandbox: {{content!r}}")
                result(ok=True, content=content)
            finally:
                cleanup_network_guard()


        def main():
            case = sys.argv[1]
            cases = {{
                "process_guard": case_process_guard,
                "network_and_subprocess_inheritance": case_network_and_subprocess_inheritance,
                "sandboxed_process_cannot_control_helper": case_sandboxed_process_cannot_control_helper,
                "landlock": case_landlock,
                "application_bootstrap": case_application_bootstrap,
                "engine_install_runtime_and_call": case_engine_install_runtime_and_call,
                "engine_stream_runtime": case_engine_stream_runtime,
                "extractor_install_runtime_and_call": case_extractor_install_runtime_and_call,
                "media_parent_requests": case_media_parent_requests,
                "extractor_calls_engine_via_sdk": case_extractor_calls_engine_via_sdk,
                "extractor_direct_engine_spawn_blocked": case_extractor_direct_engine_spawn_blocked,
                "engine_calls_mcp_direct_command": case_engine_calls_mcp_direct_command,
                "pipeline_tool_call_runs_skill_script": case_pipeline_tool_call_runs_skill_script,
                "skill_tool_call_runs_script": case_skill_tool_call_runs_script,
                "mcp_http_registry_endpoint": case_mcp_http_registry_endpoint,
                "full_boundary_chain": case_full_boundary_chain,
                "mcp_direct_command": case_mcp_direct_command,
            }}
            try:
                cases[case]()
            finally:
                cleanup_generated_paths()


        if __name__ == "__main__":
            main()
        """,
    )


@pytest.mark.parametrize(
    "case",
    [
        "process_guard",
        "network_and_subprocess_inheritance",
        "sandboxed_process_cannot_control_helper",
        "landlock",
        "application_bootstrap",
        "engine_install_runtime_and_call",
        "engine_stream_runtime",
        "extractor_install_runtime_and_call",
        "media_parent_requests",
        "extractor_calls_engine_via_sdk",
        "extractor_direct_engine_spawn_blocked",
        "engine_calls_mcp_direct_command",
        "pipeline_tool_call_runs_skill_script",
        "skill_tool_call_runs_script",
        "mcp_http_registry_endpoint",
        "full_boundary_chain",
        "mcp_direct_command",
    ],
)
def test_real_sandbox_end_to_end(case: str, sandbox_harness: Path):
    _requires_real_sandbox()
    result = _run_case(sandbox_harness, case)
    assert result["ok"] is True


def test_real_seccomp_allows_exec_and_blocks_ptrace(tmp_path: Path):
    _requires_real_sandbox()
    # exec is deliberately allowed: the core spawns processes by design
    # (orchestrator, workers, installs); exec targets are gated by Landlock
    # FS_EXECUTE rules and the process guard, not by denying the syscall.
    script_exec = _write(
        tmp_path / "seccomp_exec_probe.py",
        """
        from democrai.core.infrastructure.sandbox.os.linux.seccomp import apply_seccomp_blocklist
        apply_seccomp_blocklist()
        import os
        os.execv("/bin/true", ["/bin/true"])
        """,
    )
    completed = subprocess.run(
        [sys.executable, str(script_exec)],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=_python_env(_short_runtime_root("seccomp")),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr

    script_ptrace = _write(
        tmp_path / "seccomp_ptrace_probe.py",
        """
        from democrai.core.infrastructure.sandbox.os.linux.seccomp import apply_seccomp_blocklist
        apply_seccomp_blocklist()
        import ctypes
        import platform
        nr = 101 if platform.machine() == "x86_64" else 117
        ctypes.CDLL(None, use_errno=True).syscall(nr, 0, 0, 0, 0)
        print("ptrace_not_blocked")
        """,
    )
    completed = subprocess.run(
        [sys.executable, str(script_ptrace)],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=_python_env(_short_runtime_root("seccomp")),
        text=True,
        capture_output=True,
        timeout=10,
    )
    # The seccomp filter kills the process on a blocked syscall (SIGSYS).
    assert completed.returncode != 0
    assert "ptrace_not_blocked" not in completed.stdout
