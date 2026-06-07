from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from democrai.core.application.services.external_access import ExternalAccessApprovalRequired
from democrai.core.infrastructure.database.models import Base
from democrai.core.infrastructure.database.models import ExternalAccessRequest
from democrai.core.infrastructure.network.policy_guard import network_policy_context
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context_from_env
from democrai.core.platform.agents.models import AgentDefinition
from democrai.core.platform.agents.models import PipelineDefinition
from democrai.core.platform.agents.models import PipelineStepDefinition
import democrai.core.platform.agents.registry as agent_registry_mod
from democrai.core.platform.agents.registry import agent_registry
from democrai.core.platform.agents.registry import agent_tool_registry
from democrai.core.platform.agents.registry import pipeline_registry
from democrai.core.platform.agents.runtime import agent_runtime
from democrai.core.application.tasks.task_manager import TaskManager
from democrai.core.runtime.foundation.registry import action_registry
from democrai.core.runtime.foundation.app import RequestContext
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import reset_req_ctx
from democrai.core.runtime.foundation.app import set_req_ctx


def _preload_sdk_surface() -> None:
    import democrai.sdk.access  # noqa: F401
    import democrai.sdk.ai  # noqa: F401
    import democrai.sdk.auth  # noqa: F401
    import democrai.sdk.database  # noqa: F401
    import democrai.sdk.dependencies  # noqa: F401
    import democrai.sdk.effects  # noqa: F401
    import democrai.sdk.engines  # noqa: F401
    import democrai.sdk.environment  # noqa: F401
    import democrai.sdk.events  # noqa: F401
    import democrai.sdk.extractors  # noqa: F401
    import democrai.sdk.hooks  # noqa: F401
    import democrai.sdk.i18n  # noqa: F401
    import democrai.sdk.knowledge  # noqa: F401
    import democrai.sdk.media  # noqa: F401
    import democrai.sdk.models  # noqa: F401
    import democrai.sdk.decorator_binding  # noqa: F401
    import democrai.sdk.module_decorators  # noqa: F401
    import democrai.sdk.pages  # noqa: F401
    import democrai.sdk.system  # noqa: F401
    import democrai.sdk.tasks  # noqa: F401
    import democrai.sdk.ui  # noqa: F401


@pytest.fixture()
def external_access_db(tmp_path: Path):
    _preload_sdk_surface()
    engine = create_engine(f"sqlite:///{tmp_path / 'external_access.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    ctx = app_ctx()
    previous_db = getattr(ctx, "db", None)
    previous_logger = getattr(ctx, "logger", None)
    previous_config = getattr(ctx, "config", None)
    previous_modules = getattr(ctx, "modules", None)
    ctx.db = SimpleNamespace(get_session=lambda: SessionLocal())
    ctx.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    ctx.config = SimpleNamespace(
        get=lambda key, default=None: (
            "external-access-resume-test-key"
            if key == "app.engine_config_encryption_key"
            else default
        )
    )
    ctx.modules = SimpleNamespace(get_module=lambda _name: None)
    previous_builtin_tools_loaded = agent_registry_mod._BUILTIN_TOOLS_LOADED
    agent_registry_mod._BUILTIN_TOOLS_LOADED = True
    try:
        yield SessionLocal
    finally:
        agent_registry_mod._BUILTIN_TOOLS_LOADED = previous_builtin_tools_loaded
        ctx.db = previous_db
        ctx.logger = previous_logger
        ctx.config = previous_config
        ctx.modules = previous_modules
        Base.metadata.drop_all(engine)
        engine.dispose()


def _requests(SessionLocal):
    with SessionLocal() as session:
        return session.query(ExternalAccessRequest).all()


def _module_sdk():
    return SimpleNamespace(
        module_name="demo",
        session={
            "session_key": "sess-21",
            "user": {
                "id": 21,
                "role": "user",
                "organization_id": None,
                "access_level": 1,
            },
        },
    )


def _request_context():
    return RequestContext(
        request_id="req-21",
        user=21,
        role="user",
        organization_id=None,
        access_level=1,
        channel="ws",
        session_key="sess-21",
    )


def _approve_as_admin(
    monkeypatch,
    *,
    mode: str,
    target: Path,
    subject_name: str,
    subject_type: str = "module",
):
    from democrai.core.application.services import external_access

    monkeypatch.setattr(
        external_access,
        "get_user_access_profile",
        lambda _user_id: {
            "role": "super",
            "access_level": None,
            "organization_id": None,
        },
    )
    token = set_req_ctx(
        RequestContext(
            request_id="admin-req",
            user=1,
            role="super",
            organization_id=None,
            access_level=10,
            channel="ws",
            session_key="sess-21",
        )
    )
    try:
        if mode == "session":
            external_access.approve_for_session(
                subject_type=subject_type,
                subject_name=subject_name,
                resource_type="filesystem",
                operation="read",
                target=str(target),
                session_key="sess-21",
            )
        else:
            external_access.approve_permanently(
                subject_type=subject_type,
                subject_name=subject_name,
                resource_type="filesystem",
                operation="read",
                target=str(target),
            )
    finally:
        reset_req_ctx(token)


async def _run_with_module_guard(awaitable_factory):
    token = set_req_ctx(_request_context())
    try:
        with process_guard_context(
            subject="demo",
            subject_kind="module",
            allowed_paths=[],
            user_id=21,
            organization_id=None,
            session_key="sess-21",
            include_runtime_paths=False,
        ):
            return await awaitable_factory()
    finally:
        reset_req_ctx(token)


def test_process_guard_filesystem_denial_does_not_register_implicit_request(
    external_access_db,
    tmp_path: Path,
):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    denied = Path("/var/lib/democrai_guard_probe_denied")

    with process_guard_context(
        subject="system",
        subject_kind="module",
        allowed_paths=[str(allowed)],
        user_id=7,
        organization_id=2,
        session_key="sess-7",
    ):
        with pytest.raises(ExternalAccessApprovalRequired) as raised:
            denied.read_text(encoding="utf-8")

    assert raised.value.resource_type == "filesystem"
    assert raised.value.subject_type == "module"
    assert raised.value.subject_name == "system"
    assert "sandbox_filesystem_denied:system:" in str(raised.value)

    rows = _requests(external_access_db)
    assert rows == []


def test_process_guard_external_access_infra_error_is_not_silenced(
    external_access_db,
    tmp_path: Path,
    monkeypatch,
):
    from democrai.core.application.services import external_access
    from democrai.core.infrastructure.sandbox import process_guard

    errors: list[str] = []
    app_ctx().logger = SimpleNamespace(
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda msg, *a, **k: errors.append(str(msg)),
    )
    monkeypatch.setattr(
        external_access,
        "check_external_access",
        lambda **_kw: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    denied = tmp_path / "infra_error.txt"
    denied.write_text("x", encoding="utf-8")

    state_token = process_guard._STATE.set({"subject": "system", "subject_kind": "module"})
    cache_token = process_guard._EXTERNAL_ACCESS_CACHE.set({})
    try:
        with pytest.raises(RuntimeError) as raised:
            process_guard._external_filesystem_access_allowed(
                denied,
                operation="read",
            )
    finally:
        process_guard._EXTERNAL_ACCESS_CACHE.reset(cache_token)
        process_guard._STATE.reset(state_token)

    assert str(raised.value) == "sandbox_external_access_check_failed"
    assert any("external filesystem access check failed" in item for item in errors)


def test_process_guard_external_access_denial_is_cached_per_context(
    external_access_db,
    tmp_path: Path,
    monkeypatch,
):
    from democrai.core.application.services import external_access
    from democrai.core.infrastructure.sandbox import process_guard

    calls = {"count": 0}
    original = external_access.check_external_access

    def _counting_check(**kwargs):
        calls["count"] += 1
        return original(**kwargs)

    monkeypatch.setattr(external_access, "check_external_access", _counting_check)
    denied = tmp_path / "cached_denial.txt"
    denied.write_text("x", encoding="utf-8")

    state_token = process_guard._STATE.set({"subject": "system", "subject_kind": "module"})
    cache_token = process_guard._EXTERNAL_ACCESS_CACHE.set({})
    try:
        for _ in range(20):
            with pytest.raises(ExternalAccessApprovalRequired):
                process_guard._external_filesystem_access_allowed(
                    denied,
                    operation="read",
                )
    finally:
        process_guard._EXTERNAL_ACCESS_CACHE.reset(cache_token)
        process_guard._STATE.reset(state_token)

    assert calls["count"] == 1
    rows = _requests(external_access_db)
    assert rows == []


def test_process_guard_external_access_cache_is_scoped_by_subject_access_chain(
    tmp_path: Path,
    monkeypatch,
):
    from democrai.core.application.services import external_access
    from democrai.core.infrastructure.sandbox import process_guard

    calls = {"count": 0}

    def _deny(**_kwargs):
        calls["count"] += 1
        return SimpleNamespace(allowed=False, requires_approval=True, code="blocked")

    monkeypatch.setattr(external_access, "check_external_access", _deny)
    denied = tmp_path / "cached_chain_denial.txt"
    denied.write_text("x", encoding="utf-8")
    cache_token = process_guard._EXTERNAL_ACCESS_CACHE.set({})
    try:
        for fingerprint in (
            (("module", "system", ()), ("engine", "onnx", (("filesystem", "read", "a"),))),
            (("engine", "onnx", (("filesystem", "read", "a"),)),),
        ):
            state_token = process_guard._STATE.set(
                {
                    "subject": "onnx",
                    "subject_kind": "engine",
                    "subject_chain": [{"kind": "engine", "name": "onnx"}],
                    "subject_access_fingerprint": fingerprint,
                }
            )
            try:
                with pytest.raises(ExternalAccessApprovalRequired):
                    process_guard._external_filesystem_access_allowed(
                        denied,
                        operation="read",
                    )
            finally:
                process_guard._STATE.reset(state_token)
    finally:
        process_guard._EXTERNAL_ACCESS_CACHE.reset(cache_token)

    assert calls["count"] == 2


def test_process_guard_filesystem_denial_message_includes_subject_chain(
    external_access_db,
    tmp_path: Path,
):
    denied = tmp_path / "engine_denied.txt"
    denied.write_text("x", encoding="utf-8")

    with process_guard_context(
        subject="system",
        subject_kind="module",
        allowed_paths=[],
        user_id=7,
        organization_id=2,
        session_key="sess-7",
        include_runtime_paths=False,
    ):
        with process_guard_context(
            subject="onnx",
            subject_kind="engine",
            allowed_paths=[],
            include_runtime_paths=False,
        ):
            with pytest.raises(ExternalAccessApprovalRequired) as raised:
                denied.read_text(encoding="utf-8")

    message = str(raised.value)
    assert "sandbox_filesystem_denied:onnx:" in message
    assert "subject=engine:onnx" in message
    assert "chain=module:system > engine:onnx" in message
    assert "operation=read" in message


def test_process_guard_blocks_democrai_env_spoofing(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("DEMOCRAI_USER_ID", raising=False)
    monkeypatch.delenv("DEMOCRAI_SESSION_KEY", raising=False)
    monkeypatch.delenv("DEMOCRAI_ORGANIZATION_ID", raising=False)
    monkeypatch.delenv("DEMOCRAI_ALLOWED_PATHS", raising=False)

    with process_guard_context(
        subject="system",
        subject_kind="module",
        allowed_paths=[str(tmp_path)],
        allow_subprocess=True,
    ):
        with pytest.raises(PermissionError):
            os.environ["DEMOCRAI_USER_ID"] = "1"
        with pytest.raises(PermissionError):
            os.putenv("DEMOCRAI_SESSION_KEY", "spoof")
        os.environ["NOT_DEMOCRAI_TEST_KEY"] = "ok"

    assert os.environ.pop("NOT_DEMOCRAI_TEST_KEY") == "ok"


def test_network_guard_denial_registers_user_session_request(external_access_db):
    with network_policy_context(
        subject_name="system",
        access=[],
        user_id=8,
        organization_id=3,
        session_key="sess-8",
    ):
        with pytest.raises(ExternalAccessApprovalRequired) as raised:
            from democrai.core.infrastructure.network import policy_guard

            policy_guard._check_url("https://blocked.example/models")

    assert raised.value.resource_type == "network"
    assert raised.value.operation == "receive"
    assert raised.value.subject_type == "module"
    assert raised.value.subject_name == "system"
    assert raised.value.target == "https://blocked.example/models"

    rows = _requests(external_access_db)
    assert len(rows) == 1
    row = rows[0]
    assert row.resource_type == "network"
    assert row.operation == "receive"
    assert row.subject_type == "module"
    assert row.subject_name == "system"
    assert row.target == "https://blocked.example/models"
    assert row.requested_by == 8
    assert row.organization_id == 3
    assert row.session_key == "sess-8"


def test_session_approval_requires_pending_request_session(
    external_access_db,
    monkeypatch,
):
    denied = Path("/var/lib/democrai_guard_sessionless_probe")
    from democrai.core.application.services import external_access

    external_access.check_external_access(
        subject_type="module",
        subject_name="system",
        resource_type="filesystem",
        operation="read",
        target=str(denied),
        register_request=True,
    )

    rows = _requests(external_access_db)
    assert len(rows) == 1
    assert rows[0].session_key is None

    monkeypatch.setattr(
        external_access,
        "get_user_access_profile",
        lambda _user_id: {
            "role": "super",
            "access_level": None,
            "organization_id": None,
        },
    )
    token = set_req_ctx(
        RequestContext(
            request_id="admin-req",
            user=1,
            role="super",
            organization_id=None,
            access_level=10,
            channel="ws",
            session_key="admin-session",
        )
    )
    try:
        with pytest.raises(PermissionError) as raised:
            external_access.approve_for_session(
                subject_type="module",
                subject_name="system",
                resource_type="filesystem",
                operation="read",
                target=str(denied),
            )
    finally:
        reset_req_ctx(token)

    assert str(raised.value) == "access_policy_session_request_not_found"
    rows = _requests(external_access_db)
    assert rows[0].status == "pending"


def test_resume_action_runs_after_approval_with_original_request_context(
    external_access_db,
    monkeypatch,
):
    from democrai.core.application.services import external_access

    called: list[dict] = []
    saved_actions = dict(action_registry.actions)

    async def _resume_action(ctx, session, sdk):
        current = __import__(
            "democrai.core.runtime.foundation.app",
            fromlist=["req_ctx"],
        ).req_ctx()
        called.append(
            {
                "ctx": dict(ctx),
                "session": dict(session),
                "sdk_module": sdk.module_name,
                "request_user": current.user,
                "request_session": current.session_key,
                "action_name": current.action_name,
            }
        )
        return {"ok": True}

    action_registry.register_action("system.resume_demo", _resume_action)
    monkeypatch.setattr(
        external_access,
        "get_user_access_profile",
        lambda _user_id: {
            "role": "super",
            "access_level": None,
            "organization_id": None,
        },
    )
    monkeypatch.setattr("democrai.core.application.auth.service.get_user_permissions", lambda _user_id: [])
    try:
        request_token = set_req_ctx(
            RequestContext(
                request_id="user-req",
                user=21,
                role="user",
                organization_id=None,
                access_level=1,
                channel="ws",
                session_key="sess-21",
            )
        )
        try:
            external_access.check_external_access(
                subject_type="module",
                subject_name="system",
                resource_type="filesystem",
                operation="read",
                target="/var/lib/resume-demo",
                register_request=True,
                resume_action="system.resume_demo",
                resume_context={"inventory_id": 9},
            )
        finally:
            reset_req_ctx(request_token)
        token = set_req_ctx(
            RequestContext(
                request_id="admin-req",
                user=1,
                role="super",
                organization_id=None,
                access_level=10,
                channel="ws",
                session_key="admin-session",
            )
        )
        try:
            external_access.approve_for_session(
                subject_type="module",
                subject_name="system",
                resource_type="filesystem",
                operation="read",
                target="/var/lib/resume-demo",
                session_key="sess-21",
            )
        finally:
            reset_req_ctx(token)
    finally:
        action_registry.actions = saved_actions

    assert called == [
        {
            "ctx": {"inventory_id": 9},
            "session": {
                "session_key": "sess-21",
                "user": {"id": 21},
                "_dispatch_depth": 1,
            },
            "sdk_module": "core",
            "request_user": 21,
            "request_session": "sess-21",
            "action_name": "system.resume_demo",
        }
    ]


def test_approval_without_resume_action_does_not_run_resume(
    external_access_db,
    monkeypatch,
):
    from democrai.core.application.services import external_access

    called: list[dict] = []
    saved_actions = dict(action_registry.actions)

    async def _resume_action(ctx, session, sdk):
        called.append({"ctx": ctx, "session": session, "sdk": sdk.module_name})
        return {"ok": True}

    action_registry.register_action("system.resume_demo", _resume_action)
    monkeypatch.setattr(
        external_access,
        "get_user_access_profile",
        lambda _user_id: {
            "role": "super",
            "access_level": None,
            "organization_id": None,
        },
    )
    try:
        request_token = set_req_ctx(
            RequestContext(
                request_id="user-req",
                user=21,
                role="user",
                organization_id=None,
                access_level=1,
                channel="ws",
                session_key="sess-21",
            )
        )
        try:
            external_access.check_external_access(
                subject_type="module",
                subject_name="system",
                resource_type="filesystem",
                operation="read",
                target="/var/lib/no-resume-demo",
                register_request=True,
            )
        finally:
            reset_req_ctx(request_token)
        token = set_req_ctx(
            RequestContext(
                request_id="admin-req",
                user=1,
                role="super",
                organization_id=None,
                access_level=10,
                channel="ws",
                session_key="admin-session",
            )
        )
        try:
            external_access.approve_for_session(
                subject_type="module",
                subject_name="system",
                resource_type="filesystem",
                operation="read",
                target="/var/lib/no-resume-demo",
                session_key="sess-21",
            )
        finally:
            reset_req_ctx(token)
    finally:
        action_registry.actions = saved_actions

    assert called == []


@pytest.mark.asyncio
async def test_agent_tool_access_block_approval_and_retry_with_subject_chain(
    external_access_db,
    tmp_path: Path,
    monkeypatch,
):
    from democrai.core.infrastructure.sandbox import process_guard

    saved_tools = dict(agent_tool_registry._tools)
    denied = tmp_path / "blocked_tool.txt"
    denied.write_text("tool-ok", encoding="utf-8")

    def _read_tool(path: str):
        return Path(path).read_text(encoding="utf-8")

    agent_tool_registry.register(
        "demo.read-tool",
        _read_tool,
        module_name="demo",
    )
    try:
        with pytest.raises(ExternalAccessApprovalRequired):
            await _run_with_module_guard(
                lambda: agent_runtime.run_tool(
                    "demo.read-tool",
                    arguments={"path": str(denied)},
                )
        )

        rows = _requests(external_access_db)
        assert rows == []

        _approve_as_admin(
            monkeypatch,
            mode="permanent",
            target=denied,
            subject_name="demo.read-tool",
            subject_type="tool",
        )
        result = await _run_with_module_guard(
            lambda: agent_runtime.run_tool(
                "demo.read-tool",
                arguments={"path": str(denied)},
            )
        )
        assert result == "tool-ok"
    finally:
        agent_tool_registry._tools = saved_tools


@pytest.mark.parametrize(
    ("subject_kind", "subject_name"),
    [
        ("engine", "demo.engine"),
        ("extractor", "demo.extractor"),
    ],
)
def test_nested_engine_and_extractor_access_block_approval_and_retry(
    external_access_db,
    tmp_path: Path,
    monkeypatch,
    subject_kind: str,
    subject_name: str,
):
    from democrai.core.infrastructure.sandbox import process_guard

    denied = tmp_path / f"blocked_{subject_kind}.txt"
    denied.write_text(f"{subject_kind}-ok", encoding="utf-8")

    def _read_nested():
        with process_guard_context(
            subject="demo",
            subject_kind="module",
            allowed_paths=[],
            user_id=21,
            organization_id=None,
            session_key="sess-21",
            include_runtime_paths=False,
        ):
            with process_guard_context(
                subject=subject_name,
                subject_kind=subject_kind,
                allowed_paths=[],
                include_runtime_paths=False,
            ):
                return denied.read_text(encoding="utf-8")

    with pytest.raises(ExternalAccessApprovalRequired):
        _read_nested()

    rows = _requests(external_access_db)
    assert rows == []

    _approve_as_admin(
        monkeypatch,
        mode="permanent",
        target=denied,
        subject_name=subject_name,
        subject_type=subject_kind,
    )
    assert _read_nested() == f"{subject_kind}-ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("session_key", ["sess-21", None])
async def test_background_task_access_block_approval_and_retry(
    external_access_db,
    tmp_path: Path,
    monkeypatch,
    session_key: str | None,
):
    from democrai.core.infrastructure.sandbox import process_guard

    ctx = app_ctx()
    monkeypatch.setattr(process_guard, "_runtime_filesystem_read_paths", lambda: [])
    previous_task_manager = getattr(ctx, "task_manager", None)
    previous_modules = getattr(ctx, "modules", None)
    manager = TaskManager()
    ctx.task_manager = manager
    ctx.modules = SimpleNamespace(get_module=lambda _name: SimpleNamespace(access=[]))
    denied = tmp_path / f"blocked_task_{session_key or 'none'}.txt"
    denied.write_text("task-ok", encoding="utf-8")

    async def _task(path: str):
        return Path(path).read_text(encoding="utf-8")

    async def _submit_once():
        task_id = await manager.submit(
            21,
            _task(str(denied)),
            "sandbox task",
            module="demo",
            organization_id=None,
        )
        task = manager.get_task(task_id)
        await task._asyncio_task
        return task

    try:
        if session_key:
            token = set_req_ctx(
                RequestContext(
                    request_id="task-req",
                    user=21,
                    role="user",
                    organization_id=None,
                    access_level=1,
                    channel="ws",
                    session_key=session_key,
                )
            )
            try:
                first = await _submit_once()
            finally:
                reset_req_ctx(token)
        else:
            first = await _submit_once()

        assert first.status == "failed"
        rows = _requests(external_access_db)
        assert rows == []

        _approve_as_admin(
            monkeypatch,
            mode="permanent",
            target=denied,
            subject_name="demo",
        )

        if session_key:
            token = set_req_ctx(
                RequestContext(
                    request_id="task-retry",
                    user=21,
                    role="user",
                    organization_id=None,
                    access_level=1,
                    channel="ws",
                    session_key=session_key,
                )
            )
            try:
                second = await _submit_once()
            finally:
                reset_req_ctx(token)
        else:
            second = await _submit_once()

        assert second.status == "completed"
        assert second.result == "task-ok"
    finally:
        ctx.task_manager = previous_task_manager
        ctx.modules = previous_modules


@pytest.mark.asyncio
async def test_agent_handler_access_block_approval_and_retry_with_subject_chain(
    external_access_db,
    tmp_path: Path,
    monkeypatch,
):
    from democrai.core.infrastructure.sandbox import process_guard

    saved_agents = dict(agent_registry._agents)
    denied = tmp_path / "blocked_agent.txt"
    denied.write_text("agent-ok", encoding="utf-8")

    async def _agent_handler(input: str = ""):
        return Path(input).read_text(encoding="utf-8")

    agent_registry.register(
        AgentDefinition(
            name="demo.reader-agent",
            description="reader",
            module_name="demo",
            handler=_agent_handler,
        )
    )
    try:
        with pytest.raises(ExternalAccessApprovalRequired):
            await _run_with_module_guard(
                lambda: agent_runtime.run_agent(
                    "demo.reader-agent",
                    input=str(denied),
                )
            )

        rows = _requests(external_access_db)
        assert rows == []

        _approve_as_admin(
            monkeypatch,
            mode="permanent",
            target=denied,
            subject_name="demo.reader-agent",
            subject_type="agent",
        )
        result = await _run_with_module_guard(
            lambda: agent_runtime.run_agent(
                "demo.reader-agent",
                input=str(denied),
            )
        )
        assert result.content == "agent-ok"
    finally:
        agent_registry._agents = saved_agents


@pytest.mark.asyncio
async def test_pipeline_agent_tool_access_block_approval_and_retry_with_deep_subject_chain(
    external_access_db,
    tmp_path: Path,
    monkeypatch,
):
    from democrai.core.infrastructure.sandbox import process_guard

    saved_tools = dict(agent_tool_registry._tools)
    saved_agents = dict(agent_registry._agents)
    saved_pipelines = dict(pipeline_registry._pipelines)
    denied = tmp_path / "blocked_pipeline.txt"
    denied.write_text("pipeline-ok", encoding="utf-8")

    def _read_tool(path: str):
        return Path(path).read_text(encoding="utf-8")

    async def _agent_handler(input: str = "", context=None):
        return await agent_runtime.run_tool(
            "demo.pipeline-tool",
            arguments={"path": input},
            context=context,
        )

    agent_tool_registry.register(
        "demo.pipeline-tool",
        _read_tool,
        module_name="demo",
    )
    agent_registry.register(
        AgentDefinition(
            name="demo.pipeline-agent",
            description="pipeline agent",
            module_name="demo",
            handler=_agent_handler,
        )
    )
    pipeline_registry.register(
        PipelineDefinition(
            name="demo.deep-pipeline",
            description="pipeline",
            module_name="demo",
            steps=(
                PipelineStepDefinition(
                    kind="agent",
                    target="demo.pipeline-agent",
                    output_key="result",
                ),
            ),
        )
    )
    try:
        with pytest.raises(ExternalAccessApprovalRequired):
            await _run_with_module_guard(
                lambda: agent_runtime.run_pipeline(
                    "demo.deep-pipeline",
                    input=str(denied),
                )
            )

        rows = _requests(external_access_db)
        assert rows == []

        _approve_as_admin(
            monkeypatch,
            mode="permanent",
            target=denied,
            subject_name="demo.pipeline-tool",
            subject_type="tool",
        )
        result = await _run_with_module_guard(
            lambda: agent_runtime.run_pipeline(
                "demo.deep-pipeline",
                input=str(denied),
            )
        )
        assert result["result"] == "pipeline-ok"
    finally:
        agent_tool_registry._tools = saved_tools
        agent_registry._agents = saved_agents
        pipeline_registry._pipelines = saved_pipelines


def test_guard_contexts_inherit_request_context_when_not_passed(tmp_path: Path):
    token = set_req_ctx(
        RequestContext(
            request_id="req-1",
            user=11,
            role="user",
            organization_id=4,
            access_level=3,
            channel="ws",
            session_key="sess-11",
        )
    )
    try:
        with process_guard_context(
            subject="system",
            allowed_paths=[str(tmp_path)],
            include_runtime_paths=False,
        ):
            from democrai.core.infrastructure.sandbox import process_guard
            from democrai.core.infrastructure.network import policy_guard

            assert process_guard._request_context() == (11, 4, "sess-11")
            assert policy_guard._request_context() == (11, 4, "sess-11")
    finally:
        reset_req_ctx(token)


def test_guard_contexts_restore_user_session_from_env(monkeypatch):
    monkeypatch.setenv("DEMOCRAI_NETWORK_SUBJECT", "system")
    monkeypatch.setenv("DEMOCRAI_NETWORK_SUBJECT_KIND", "module")
    monkeypatch.setenv("DEMOCRAI_ALLOWED_NETWORK_TARGETS", "[]")
    monkeypatch.setenv("DEMOCRAI_ALLOWED_PATHS", "[]")
    monkeypatch.setenv("DEMOCRAI_USER_ID", "13")
    monkeypatch.setenv("DEMOCRAI_ORGANIZATION_ID", "5")
    monkeypatch.setenv("DEMOCRAI_SESSION_KEY", "sess-13")

    with process_guard_context_from_env():
        from democrai.core.infrastructure.sandbox import process_guard
        from democrai.core.infrastructure.network import policy_guard

        assert process_guard._request_context() == (13, 5, "sess-13")
        assert policy_guard._request_context() == (13, 5, "sess-13")
