from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest


RUN_ENV = "DEMOCRAI_RUN_REAL_SANDBOX_TESTS"


pytestmark = pytest.mark.sudo_sandbox


def _requires_real_sandbox() -> None:
    if os.environ.get(RUN_ENV) != "1":
        pytest.skip(f"set {RUN_ENV}=1 to run real macOS sandbox diagnostics")
    if sys.platform != "darwin":
        pytest.skip("real macOS sandbox diagnostics are macOS-only")
    if not (shutil.which("sandbox-exec") or Path("/usr/bin/sandbox-exec").exists()):
        raise AssertionError("macos_sandbox_exec_unavailable")


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
    return env


def _short_runtime_root(name: str) -> Path:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return Path(tempfile.gettempdir()) / f"dc-macos-{os.getpid()}-{digest}"


def _write(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _run_case(script: Path, case: str, *, timeout: int = 45) -> dict:
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

        import json
        import os
        import socket
        import sys
        from pathlib import Path


        def _control_env():
            return {
                "helper_socket": bool(os.environ.get("DEMOCRAI_OS_SANDBOX_HELPER_SOCKET")),
                "helper_token": bool(os.environ.get("DEMOCRAI_OS_SANDBOX_HELPER_TOKEN")),
                "policy_file": bool(os.environ.get("DEMOCRAI_OS_SANDBOX_POLICY_FILE")),
            }


        def _network_probe():
            opened = False
            error = ""
            try:
                socket.create_connection(("1.1.1.1", 443), timeout=1.0).close()
                opened = True
            except OSError as exc:
                error = str(exc)
            return {"direct_open": opened, "direct_error": error}


        def _filesystem_probe():
            allowed_file = Path(os.environ["DEMOCRAI_SANDBOX_ALLOWED_FILE"])
            writable_dir = Path(os.environ["DEMOCRAI_SANDBOX_WRITABLE_DIR"])
            denied_file = Path(os.environ["DEMOCRAI_SANDBOX_DENIED_FILE"])
            allowed_read = allowed_file.read_text(encoding="utf-8")
            written = writable_dir / "child-write.txt"
            written.write_text("ok", encoding="utf-8")
            denied = False
            denied_error = ""
            try:
                denied_file.read_text(encoding="utf-8")
            except OSError as exc:
                denied = True
                denied_error = str(exc)
            return {
                "allowed_read": allowed_read,
                "write_exists": written.exists(),
                "denied": denied,
                "denied_error": denied_error,
            }


        mode = sys.argv[1] if len(sys.argv) > 1 else "network"
        payload = {"mode": mode, "control_env": _control_env()}
        if mode == "filesystem":
            payload["filesystem"] = _filesystem_probe()
        else:
            payload["network"] = _network_probe()
        print(json.dumps(payload, ensure_ascii=True))
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
        import textwrap
        import threading
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
                        print("".join(traceback.format_exception(*exc_info)), file=sys.stderr)


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


        def child_access(subject_kind="module", subject="system.sudo"):
            return [
                rule(subject_kind, subject, "filesystem", "execute", sys.executable),
                rule(subject_kind, subject, "filesystem", "read", CHILD),
            ]


        def sandbox_child(mode="network", access=None, extra_env=None):
            app_config()
            from democrai.core.infrastructure.sandbox import launcher
            from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

            env = dict(os.environ)
            if extra_env:
                env.update({{str(k): str(v) for k, v in extra_env.items()}})
            with process_guard_context(
                subject="system.sudo",
                subject_kind="module",
                access=list(access or child_access()),
                allow_subprocess=True,
            ):
                completed = launcher.run_subprocess(
                    [sys.executable, CHILD, mode],
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=15,
                    env=env,
                )
            return json.loads(completed.stdout.strip().splitlines()[-1])


        def assert_runtime_env_clean(payload):
            env = payload.get("control_env") or {{}}
            if env.get("helper_socket") or env.get("helper_token") or env.get("policy_file"):
                raise AssertionError(f"runtime received control-plane env: {{env!r}}")


        def assert_network_denied(payload):
            assert_runtime_env_clean(payload)
            network = payload.get("network") or {{}}
            if network.get("direct_open"):
                raise AssertionError(f"direct network was not blocked: {{payload!r}}")


        def assert_filesystem_enforced(payload):
            assert_runtime_env_clean(payload)
            filesystem = payload.get("filesystem") or {{}}
            if filesystem.get("allowed_read") != "allowed":
                raise AssertionError(f"allowed read failed: {{payload!r}}")
            if not filesystem.get("write_exists"):
                raise AssertionError(f"allowed write failed: {{payload!r}}")
            if not filesystem.get("denied"):
                raise AssertionError(f"filesystem read outside allowlist succeeded: {{payload!r}}")


        def make_filesystem_env():
            root = track_temp_dir("democrai_macos_fs_")
            allowed = root / "allowed"
            writable = root / "writable"
            denied = root / "denied"
            allowed.mkdir()
            writable.mkdir()
            denied.mkdir()
            allowed_file = allowed / "ok.txt"
            denied_file = denied / "secret.txt"
            allowed_file.write_text("allowed", encoding="utf-8")
            denied_file.write_text("secret", encoding="utf-8")
            access = child_access() + [
                rule("module", "system.sudo", "filesystem", "read", allowed),
                rule("module", "system.sudo", "filesystem", "create", writable),
                rule("module", "system.sudo", "filesystem", "modify", writable),
            ]
            env = {{
                "DEMOCRAI_SANDBOX_ALLOWED_FILE": allowed_file,
                "DEMOCRAI_SANDBOX_WRITABLE_DIR": writable,
                "DEMOCRAI_SANDBOX_DENIED_FILE": denied_file,
            }}
            return access, env


        def set_probe_request_context():
            from democrai.core.runtime.foundation.app import RequestContext
            from democrai.core.runtime.foundation.app import app_ctx
            from democrai.core.runtime.foundation.app import set_req_ctx

            return set_req_ctx(
                RequestContext(
                    request_id="macos-sandbox-test",
                    user=1,
                    role="admin",
                    organization_id=1,
                    access_level=100,
                    channel="ipc",
                    app=app_ctx(),
                    session_key="macos-sandbox-session",
                    module_name="system",
                    stream_id="macos-sandbox-stream",
                )
            )


        def reset_probe_request_context(token):
            from democrai.core.runtime.foundation.app import reset_req_ctx

            reset_req_ctx(token)


        def _generated_module(body):
            lines = textwrap.dedent(body).splitlines()
            while lines and not lines[0].strip():
                lines.pop(0)
            first = next((line for line in lines if line.strip()), "")
            base = len(first) - len(first.lstrip())
            if base:
                lines = [line[base:] if line.startswith(" " * base) else line for line in lines]
            return "\\n".join(lines) + "\\n"


        def ensure_fake_venv_python(env_root):
            bin_dir = env_root / ".venv" / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            target = bin_dir / "python"
            if target.exists():
                return
            try:
                target.symlink_to(sys.executable)
            except Exception:
                shutil.copyfile(sys.executable, target)
                target.chmod(0o755)


        def make_fake_extensions():
            root = track_temp_dir("democrai_macos_extensions_")
            engine_root = root / "engines"
            extractor_root = root / "extractors"
            engine_pkg = engine_root / "sudo_probe_engine"
            extractor_pkg = extractor_root / "sudo_probe_extractor"
            engine_pkg.mkdir(parents=True)
            extractor_pkg.mkdir(parents=True)
            for package in (engine_root, extractor_root, engine_pkg, extractor_pkg):
                (package / "__init__.py").write_text("", encoding="utf-8")

            engine_code = textwrap.dedent('''
                import json
                import subprocess
                import sys

                CHILD = __CHILD__

                class SudoProbeEngine:
                    def __init__(self, config):
                        self.config = config

                    @classmethod
                    def _install_local(cls, **_kwargs):
                        completed = subprocess.run([sys.executable, CHILD, "network"], check=True, text=True, capture_output=True)
                        return json.loads(completed.stdout.strip())

                    @classmethod
                    def _validate_config_local(cls, **_kwargs):
                        completed = subprocess.run([sys.executable, CHILD, "network"], check=True, text=True, capture_output=True)
                        return json.loads(completed.stdout.strip())

                    def probe(self):
                        completed = subprocess.run([sys.executable, CHILD, "network"], check=True, text=True, capture_output=True)
                        return json.loads(completed.stdout.strip())

                    def call_mcp_direct(self):
                        import sudo_probe_mcp_bridge
                        return sudo_probe_mcp_bridge.invoke(CHILD)

                    async def generate_stream(self, messages, options):
                        completed = subprocess.run([sys.executable, CHILD, "network"], check=True, text=True, capture_output=True)
                        yield json.loads(completed.stdout.strip())

                    def materialize_media(self, storage_path):
                        import sudo_probe_engine_media_bridge
                        return sudo_probe_engine_media_bridge.materialize(storage_path)
            ''').replace("__CHILD__", repr(CHILD))

            extractor_code = textwrap.dedent('''
                import json
                import subprocess
                import sys

                CHILD = __CHILD__

                class SudoProbeExtractor:
                    extractor_id = "sudo_probe_extractor"

                    def __init__(self, config=None):
                        self._config = config

                    @classmethod
                    def _install_local(cls, **_kwargs):
                        completed = subprocess.run([sys.executable, CHILD, "network"], check=True, text=True, capture_output=True)
                        return json.loads(completed.stdout.strip())

                    @classmethod
                    def _check_ready_local(cls, **_kwargs):
                        return {{"ready": True}}

                    @classmethod
                    def probe_self(cls):
                        completed = subprocess.run([sys.executable, CHILD, "network"], check=True, text=True, capture_output=True)
                        return json.loads(completed.stdout.strip())

                    @classmethod
                    def probe_subprocess(cls):
                        completed = subprocess.run([sys.executable, CHILD, "network"], check=True, text=True, capture_output=True)
                        return json.loads(completed.stdout.strip())

                    @classmethod
                    async def call_engine_via_sdk(cls):
                        import sudo_probe_sdk_bridge
                        from democrai.sdk.client import active_sdk
                        sudo_probe_sdk_bridge.patch_sdk_ai()
                        resolved = await active_sdk.ai.get_provider_by_model_registry_id(1)
                        provider = resolved.get("provider")
                        if provider is None:
                            raise RuntimeError("provider_missing")
                        return await provider.generate_completion(messages=[], options={{}})

                    @classmethod
                    def materialize_media(cls, storage_path):
                        import sudo_probe_extractor_media_bridge
                        return sudo_probe_extractor_media_bridge.materialize(storage_path)
            ''').replace("__CHILD__", repr(CHILD))

            sdk_bridge_code = _generated_module('''
                class _SudoProbeProvider:
                    async def generate_completion(self, messages=None, options=None):
                        return {{"status": "ok", "remote_provider": True, "orchestrator_boundary": True}}

                async def _get_provider_by_model_registry_id(self, model_registry_id, *, confirm_swap=False):
                    return {{"status": "ok", "provider": _SudoProbeProvider()}}

                def patch_sdk_ai():
                    from democrai.sdk.ai import AI
                    AI.get_provider_by_model_registry_id = _get_provider_by_model_registry_id
            ''')
            engine_media_bridge_code = _generated_module('''
                import uuid
                from democrai.core.application.ai.engine.runtime.serialization import json_value
                from democrai.core.application.ai.engine.runtime.serialization import python_value
                from democrai.core.runtime.ipc.local_connection import connect_from_env

                def materialize(storage_path):
                    conn = connect_from_env("DEMOCRAI_ENGINE_WORKER_PARENT")
                    request_id = uuid.uuid4().hex
                    try:
                        conn.send(json_value({{"id": request_id, "parent_request": True, "operation": "media.materialize", "payload": {{"storage_path": storage_path}}}}))
                        while True:
                            response = python_value(conn.recv())
                            if str(response.get("id") or "") == request_id:
                                if not response.get("ok"):
                                    raise RuntimeError(str(response.get("error") or "engine_parent_media_error"))
                                return response.get("result")
                    finally:
                        conn.close()
            ''')
            extractor_media_bridge_code = _generated_module('''
                def materialize(storage_path):
                    from democrai.core.runtime.foundation.app import app_ctx
                    materialized = app_ctx().media.get_path(storage_path)
                    return {{"path": str(materialized.path), "temporary": bool(materialized.temporary)}}
            ''')
            mcp_bridge_code = _generated_module('''
                import sys

                def invoke(child):
                    import democrai.core.platform.mcp.runtime as mcp_runtime_mod
                    from democrai.core.platform.mcp.registry import McpServerRecord
                    mcp_runtime_mod.get_server_by_name = lambda name: McpServerRecord(
                        id=1,
                        name=name,
                        transport="direct",
                        endpoint_url="",
                        config={{"command": [sys.executable], "args": [child, "network"]}},
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
            from democrai.core.runtime.dependencies.engine_env import get_engine_local_env_path, get_engine_venv_site_packages_path
            from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_env_path, get_extractor_venv_site_packages_path

            ensure_fake_venv_python(get_engine_local_env_path("sudo_probe_engine"))
            ensure_fake_venv_python(get_extractor_local_env_path("sudo_probe_extractor"))
            CLEANUP_PATHS.append(get_engine_local_env_path("sudo_probe_engine"))
            CLEANUP_PATHS.append(get_extractor_local_env_path("sudo_probe_extractor"))
            engine_env_root = get_engine_venv_site_packages_path("sudo_probe_engine")
            extractor_env_root = get_extractor_venv_site_packages_path("sudo_probe_extractor")
            (engine_env_root / "sudo_probe_engine").mkdir(parents=True, exist_ok=True)
            (extractor_env_root / "sudo_probe_extractor").mkdir(parents=True, exist_ok=True)
            (engine_env_root / "sudo_probe_engine" / "__init__.py").write_text("", encoding="utf-8")
            (extractor_env_root / "sudo_probe_extractor" / "__init__.py").write_text("", encoding="utf-8")
            (engine_env_root / "sudo_probe_engine" / "engine.py").write_text(engine_code, encoding="utf-8")
            (extractor_env_root / "sudo_probe_extractor" / "extractor.py").write_text(extractor_code, encoding="utf-8")
            (extractor_env_root / "sudo_probe_sdk_bridge.py").write_text(sdk_bridge_code, encoding="utf-8")
            (engine_env_root / "sudo_probe_engine_media_bridge.py").write_text(engine_media_bridge_code, encoding="utf-8")
            (extractor_env_root / "sudo_probe_extractor_media_bridge.py").write_text(extractor_media_bridge_code, encoding="utf-8")
            (engine_env_root / "sudo_probe_mcp_bridge.py").write_text(mcp_bridge_code, encoding="utf-8")

            access = [
                {{"resource_type": "filesystem", "operation": "execute", "target": sys.executable}},
                {{"resource_type": "filesystem", "operation": "read", "target": CHILD}},
                {{"resource_type": "filesystem", "operation": "read", "target": str(root)}},
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
            os.environ["PYTHONPATH"] = os.pathsep.join(python_paths)
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


        class FakeMediaProvider:
            def __init__(self):
                self.root = track_temp_dir("democrai_macos_media_")
                self.source = self.root / "source.bin"
                self.source.write_bytes(b"sudo sandbox media")

            def get_path(self, storage_path, destination_dir=None):
                if storage_path != "probe://media":
                    raise FileNotFoundError(storage_path)
                destination = Path(destination_dir) if destination_dir else self.root
                destination.mkdir(parents=True, exist_ok=True)
                target = destination / "materialized.bin"
                shutil.copyfile(self.source, target)
                return SimpleNamespace(path=str(target), temporary=True, cleanup=lambda: None)


        def make_fake_skill():
            root = track_temp_dir("democrai_macos_skill_")
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "probe.py").write_text(
                textwrap.dedent('''
                import json
                import socket
                import subprocess
                import sys

                completed = subprocess.run([sys.executable, "-c", "print('nested-ok')"], check=True, text=True, capture_output=True)
                network_blocked = False
                try:
                    socket.create_connection(("1.1.1.1", 443), timeout=1.0).close()
                except OSError:
                    network_blocked = True
                print(json.dumps({{"nested_returncode": completed.returncode, "network_blocked": network_blocked}}))
                '''),
                encoding="utf-8",
            )
            from democrai.core.platform.agents.models import SkillDefinition, SkillMetadata
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


        def case_process_guard():
            app_config()
            from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

            blocked = False
            with process_guard_context(subject="sudo.process_guard", subject_kind="module", access=[], allow_subprocess=False):
                try:
                    subprocess.run([sys.executable, CHILD], check=False)
                except (PermissionError, RuntimeError) as exc:
                    blocked = isinstance(exc, PermissionError) or str(exc) == "sandbox_external_access_check_failed"
            if not blocked:
                raise AssertionError("process_guard did not block unapproved subprocess")
            result(ok=True, blocked=blocked)


        def case_network_and_subprocess_inheritance():
            payload = sandbox_child("network")
            assert_network_denied(payload)
            result(ok=True, payload=payload)


        def case_sandboxed_process_cannot_control_helper():
            attacker = track_temp_dir("democrai_macos_helper_attack_") / "helper_attack.py"
            attacker.write_text(_generated_module('''
                import json
                import os
                import socket
                from pathlib import Path

                payload = {{"helper_modified": False, "policy_written": False, "policy_error": None, "attempts": [], "network_open": False}}
                try:
                    Path(os.environ["DEMOCRAI_OS_SANDBOX_POLICY_FILE"]).write_text('{{"endpoints":[]}}', encoding="utf-8")
                    payload["policy_written"] = True
                except Exception as exc:
                    payload["policy_error"] = str(exc)
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    try:
                        sock.settimeout(2.0)
                        sock.connect(os.environ["DEMOCRAI_OS_SANDBOX_HELPER_SOCKET"])
                        request = {{"action": "clear", "pid": os.getpid(), "token": "definitely-wrong-token"}}
                        sock.sendall((json.dumps(request) + "\\\\n").encode("utf-8"))
                        response = json.loads(sock.recv(4096).decode("utf-8"))
                        payload["attempts"].append({{"operation": "clear_bad_token", "response": response}})
                        if response.get("ok"):
                            payload["helper_modified"] = True
                    except Exception as exc:
                        payload["attempts"].append({{"operation": "clear_bad_token", "error": str(exc)}})
                    finally:
                        sock.close()
                except Exception as exc:
                    payload["helper_error"] = str(exc)
                try:
                    socket.create_connection(("1.1.1.1", 443), timeout=1.0).close()
                    payload["network_open"] = True
                except OSError as exc:
                    payload["network_error"] = str(exc)
                print(json.dumps(payload, ensure_ascii=True))
            '''), encoding="utf-8")
            access = child_access() + [
                rule("module", "system.sudo", "filesystem", "read", attacker),
            ]
            app_config()
            from democrai.core.infrastructure.sandbox import launcher
            from democrai.core.infrastructure.sandbox.os.helper import (
                ensure_os_sandbox_helper_ready,
                get_os_sandbox_helper_socket_path,
                get_os_sandbox_policy_file_path,
            )
            from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
            ensure_os_sandbox_helper_ready()
            env = dict(os.environ)
            env["DEMOCRAI_OS_SANDBOX_HELPER_SOCKET"] = get_os_sandbox_helper_socket_path()
            env["DEMOCRAI_OS_SANDBOX_POLICY_FILE"] = get_os_sandbox_policy_file_path()
            env.pop("DEMOCRAI_OS_SANDBOX_HELPER_TOKEN", None)
            with process_guard_context(subject="system.sudo", subject_kind="module", access=access, allow_subprocess=True):
                completed = launcher.run_subprocess([sys.executable, str(attacker)], check=False, text=True, capture_output=True, timeout=15, env=env)
            if completed.returncode != 0:
                raise AssertionError(
                    f"sandboxed helper attacker failed rc={{completed.returncode}} stdout={{completed.stdout!r}} stderr={{completed.stderr!r}}"
                )
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
            if payload.get("policy_written") or not payload.get("policy_error"):
                raise AssertionError(f"sandboxed process policy write result invalid: {{payload!r}}")
            if payload.get("helper_modified"):
                raise AssertionError(f"sandboxed process modified helper-controlled network rules: {{payload!r}}")
            helper_attempts = payload.get("attempts") or []
            if not helper_attempts:
                raise AssertionError(f"sandboxed process did not exercise helper socket: {{payload!r}}")
            if payload.get("network_open"):
                raise AssertionError(f"sandboxed process opened direct network after helper attack: {{payload!r}}")
            result(ok=True, payload=payload)


        def case_seatbelt_filesystem_enforcement():
            access, env = make_filesystem_env()
            payload = sandbox_child("filesystem", access=access, extra_env=env)
            assert_filesystem_enforced(payload)
            result(ok=True, payload=payload)


        def case_application_bootstrap():
            cfg = app_config()
            os.environ["DEMOCRAI_CORE_OS_SANDBOX_REEXEC"] = "1"
            from democrai.core.infrastructure.sandbox.os.bootstrap import bootstrap_current_process_os_sandbox
            from democrai.core.runtime.foundation.app import app_ctx
            details = bootstrap_current_process_os_sandbox(app_ctx(), reason="macos_real_sandbox_test", mode="test")
            if not details:
                raise AssertionError("application bootstrap returned no details")
            result(ok=True, details=details, enabled=cfg.get("sandbox.os.enabled", False))


        def case_engine_install_runtime_and_call():
            make_fake_extensions()
            from democrai.core.application.ai.engine.runtime.methods import invoke_engine_class_method
            from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject
            request_token = set_probe_request_context()
            try:
                install = invoke_engine_class_method(engine_id="sudo_probe_engine", phase="install", method="_install_local", payload={{}})
                validation = invoke_engine_class_method(engine_id="sudo_probe_engine", phase="runtime", method="_validate_config_local", payload={{"config": {{}}}}, config={{}})
                subject = EngineWorkerSubject(engine_id="sudo_probe_engine", config={{"model": "demo"}})
                try:
                    worker_probe = subject.invoke("probe", {{}})
                finally:
                    subject.close()
            finally:
                reset_probe_request_context(request_token)
            for payload in (install, validation, worker_probe):
                assert_network_denied(payload)
            result(ok=True, install=install, validation=validation, worker=worker_probe)


        def case_engine_stream_runtime():
            make_fake_extensions()
            from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject
            request_token = set_probe_request_context()
            try:
                subject = EngineWorkerSubject(engine_id="sudo_probe_engine", config={{"model": "demo"}})
                try:
                    async def _collect():
                        items = []
                        async for item in subject.invoke_stream("generate_stream", {{"messages": [], "options": {{}}}}):
                            items.append(item)
                        return items
                    chunks = asyncio.run(_collect())
                finally:
                    subject.close()
            finally:
                reset_probe_request_context(request_token)
            if not chunks:
                raise AssertionError("engine stream produced no chunks")
            assert_network_denied(chunks[0])
            result(ok=True, chunks=chunks)


        def case_extractor_install_runtime_and_call():
            make_fake_extensions()
            from democrai.core.application.knowledge.extractor.worker_subject import ExtractorWorkerSubject
            request_token = set_probe_request_context()
            try:
                for phase in ("install", "runtime"):
                    subject = ExtractorWorkerSubject(extractor_id="sudo_probe_extractor", phase=phase, config={{}})
                    try:
                        payload = subject.invoke_class("probe_subprocess", {{}})
                    finally:
                        subject.close()
                    assert_network_denied(payload)
            finally:
                reset_probe_request_context(request_token)
            result(ok=True)


        def case_media_parent_requests():
            make_fake_extensions()
            from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject
            from democrai.core.application.knowledge.extractor.worker_subject import ExtractorWorkerSubject
            from democrai.core.runtime.foundation.app import app_ctx
            app_ctx().media = FakeMediaProvider()
            request_token = set_probe_request_context()
            try:
                engine_subject = EngineWorkerSubject(engine_id="sudo_probe_engine", config={{"model": "demo"}})
                try:
                    engine_payload = engine_subject.invoke("materialize_media", {{"storage_path": "probe://media"}})
                finally:
                    engine_subject.close()
                extractor_subject = ExtractorWorkerSubject(extractor_id="sudo_probe_extractor", phase="runtime", config={{}})
                try:
                    extractor_payload = extractor_subject.invoke_class("materialize_media", {{"storage_path": "probe://media"}})
                finally:
                    extractor_subject.close()
            finally:
                reset_probe_request_context(request_token)
            for payload in (engine_payload, extractor_payload):
                path = Path(str(payload.get("path") or ""))
                if not path.is_file() or path.read_bytes() != b"sudo sandbox media":
                    raise AssertionError(f"media materialization failed: {{payload!r}}")
            result(ok=True, engine=engine_payload, extractor=extractor_payload)


        def case_extractor_calls_engine_via_sdk():
            make_fake_extensions()
            from democrai.core.application.knowledge.extractor.worker_subject import ExtractorWorkerSubject
            request_token = set_probe_request_context()
            try:
                subject = ExtractorWorkerSubject(extractor_id="sudo_probe_extractor", phase="runtime", config={{}})
                try:
                    payload = subject.invoke_class("call_engine_via_sdk", {{}})
                finally:
                    subject.close()
            finally:
                reset_probe_request_context(request_token)
            boundary = bool(payload.get("orchestrator_boundary")) or bool(
                payload.get("engine", {{}}).get("orchestrator_boundary")
            )
            if not payload.get("remote_provider") or not boundary:
                raise AssertionError(f"extractor SDK did not use orchestrator boundary: {{payload!r}}")
            result(ok=True, payload=payload)


        def case_extractor_direct_engine_spawn_blocked():
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
                subject = ExtractorWorkerSubject(extractor_id="sudo_probe_extractor", phase="runtime", config={{}})
                try:
                    subject.invoke_class("probe_self", {{}})
                finally:
                    subject.close()
            except RuntimeError as exc:
                error = str(exc)
                blocked = "extractor_sdk_boundary_violation" in error
            if not blocked:
                raise AssertionError(f"extractor direct core import was not blocked: {{error}}")
            result(ok=True, blocked=blocked, error=error.split("\\n", 1)[0])


        def case_engine_calls_mcp_direct_command():
            make_fake_extensions()
            from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject
            request_token = set_probe_request_context()
            try:
                subject = EngineWorkerSubject(engine_id="sudo_probe_engine", config={{"model": "demo"}})
                try:
                    payload = subject.invoke("call_mcp_direct", {{}})
                finally:
                    subject.close()
            finally:
                reset_probe_request_context(request_token)
            assert_network_denied(payload)
            result(ok=True, payload=payload)


        def _run_skill_tool():
            make_fake_skill()
            from democrai.sdk.client import SDK
            SDK("", "core", session={{"user": {{"id": 1, "organization_id": 1}}}})
            from democrai.core.application.ai.pipeline_context import ai_pipeline_context, create_ai_pipeline_context
            from democrai.core.platform.agents.tool_runtime import agent_tool_runtime

            async def _run():
                context = create_ai_pipeline_context(root_method="macos_sandbox_skill_tool", request_id="macos-sandbox-skill-tool")
                context.selected_skills = ("system.sudo_probe_skill",)
                with ai_pipeline_context(context):
                    return await agent_tool_runtime.run_tool(
                        "core.run-skill-script",
                        arguments={{"skill": "system.sudo_probe_skill", "script": "probe.py", "timeout_seconds": 10}},
                        context={{"module_name": "system"}},
                        module_name="system",
                    )
            request_token = set_probe_request_context()
            try:
                payload = asyncio.run(_run())
            finally:
                reset_probe_request_context(request_token)
            if payload.get("returncode") != 0:
                raise AssertionError(f"skill script failed: {{payload!r}}")
            script_payload = json.loads(str(payload.get("stdout") or "").strip().splitlines()[-1])
            if not script_payload.get("network_blocked") or script_payload.get("nested_returncode") != 0:
                raise AssertionError(f"skill script sandbox behavior invalid: {{payload!r}}")
            return payload, script_payload


        def case_skill_tool_call_runs_script():
            payload, script_payload = _run_skill_tool()
            result(ok=True, payload=payload, script=script_payload)


        def case_pipeline_tool_call_runs_skill_script():
            payload, script_payload = _run_skill_tool()
            result(ok=True, payload=payload, script=script_payload)


        def case_mcp_http_registry_endpoint():
            server = None
            try:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                from democrai.core.infrastructure.database.models import Base, McpServerRegistry
                from democrai.core.runtime.foundation.app import app_ctx

                class Handler(http.server.BaseHTTPRequestHandler):
                    def do_POST(self):
                        length = int(self.headers.get("Content-Length", "0"))
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                        body = json.dumps({{"jsonrpc": "2.0", "id": payload.get("id"), "result": {{"content": {{"ok": True, "method": payload.get("method")}}}}}}).encode("utf-8")
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
                db_path = track_temp_dir("democrai_macos_mcp_db_") / "mcp.sqlite"
                app_ctx().config.values["database.url"] = f"sqlite:///{{db_path}}"
                engine = create_engine(f"sqlite:///{{db_path}}")
                Base.metadata.create_all(engine)
                Session = sessionmaker(bind=engine)
                with Session() as session:
                    session.add(McpServerRegistry(name="sudo_http_probe", transport="http", endpoint_url=f"http://127.0.0.1:{{server.server_port}}/mcp", config_encrypted="", enabled=True, timeout_ms=5000))
                    session.commit()
                from democrai.core.platform.mcp.runtime import McpRuntime
                content = McpRuntime().invoke_tool(full_name="mcp.sudo_http_probe.echo", arguments={{"ping": True}}, module_name="system")
                if not isinstance(content, dict) or not content.get("ok"):
                    raise AssertionError(f"mcp http content invalid: {{content!r}}")
                result(ok=True, content=content)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()


        def case_mcp_direct_command():
            import democrai.core.platform.mcp.runtime as mcp_runtime_mod
            from democrai.core.platform.mcp.registry import McpServerRecord
            mcp_runtime_mod.get_server_by_name = lambda name: McpServerRecord(id=1, name=name, transport="direct", endpoint_url="", config={{"command": [sys.executable], "args": [CHILD, "network"]}}, enabled=True, timeout_ms=5000)
            content = mcp_runtime_mod.McpRuntime().invoke_tool(full_name="mcp.sudo_probe.echo", arguments={{"ping": True}}, module_name="system")
            assert_network_denied(content)
            result(ok=True, content=content)


        def case_full_boundary_chain():
            make_fake_extensions()
            payload, script_payload = _run_skill_tool()
            os.environ.pop("DEMOCRAI_SANDBOX_SPAWN_BROKER_SOCKET", None)
            os.environ.pop("DEMOCRAI_SANDBOX_SPAWN_BROKER_TOKEN", None)
            case_mcp_direct_command()
            if payload.get("returncode") != 0 or not script_payload.get("network_blocked"):
                raise AssertionError("full boundary chain skill segment failed")
            result(ok=True, markers=["engine", "tool", "skill", "mcp_direct"])


        def main():
            app_config()
            case = sys.argv[1]
            cases = {{
                "process_guard": case_process_guard,
                "network_and_subprocess_inheritance": case_network_and_subprocess_inheritance,
                "sandboxed_process_cannot_control_helper": case_sandboxed_process_cannot_control_helper,
                "seatbelt_filesystem_enforcement": case_seatbelt_filesystem_enforcement,
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
            sys.stdout.flush()
            sys.stderr.flush()


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
        "seatbelt_filesystem_enforcement",
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
def test_real_sandbox_end_to_end_macos(case: str, sandbox_harness: Path):
    _requires_real_sandbox()
    payload = _run_case(sandbox_harness, case)
    assert payload["ok"] is True
