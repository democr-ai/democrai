from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.application.ai.pipeline_context import ai_pipeline_context
from democrai.core.application.ai.pipeline_context import create_ai_pipeline_context
from democrai.core.platform.agents.execution_context import AgentExecutionContext
from democrai.core.platform.agents.execution_context import current_agent_execution
from democrai.core.platform.agents.models import (
    AgentDefinition,
    AgentRunResult,
    AgentToolDefinition,
    PipelineDefinition,
    PipelineStepDefinition,
)
import democrai.core.platform.agents.runtime as runtime_mod
from democrai.core.platform.agents.skills import SkillLoader
from democrai.core.platform.agents.registry import agent_tool_registry


def _install_agent_runtime_stubs(monkeypatch):
    monkeypatch.setattr(
        runtime_mod,
        "_agent_runtime_config",
        lambda _agent_name: {
            "extra_tools": (),
            "extra_skills": (),
            "extra_mcp_servers": (),
            "extra_agents": (),
            "max_iterations": None,
        },
    )
    monkeypatch.setattr(
        runtime_mod,
        "resolve_agent_provider",
        lambda _definition, parent_provider=None: __import__("asyncio").sleep(
            0, result=parent_provider
        ),
    )
    class _Guard:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.sandbox.process_guard",
        SimpleNamespace(
            process_guard_context=lambda **_k: _Guard(),
            process_guard_bypass_context=lambda: _Guard(),
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.mcp.runtime",
        SimpleNamespace(
            mcp_runtime=SimpleNamespace(
                list_agent_tool_definitions_async=lambda **_k: __import__("asyncio").sleep(0, result=[]),
                invoke_tool_async=lambda **_k: __import__("asyncio").sleep(0, result={"mcp": True}),
            )
        ),
    )


def test_skill_loader_discovery_and_assets(tmp_path: Path, monkeypatch):
    import democrai.core.application.access_policy.models as access_models

    monkeypatch.setattr(access_models, "_SUBJECT_TYPES", {*access_models._SUBJECT_TYPES, "skill"})
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    mod_root = tmp_path / "mods"
    for root in (builtin, user):
        (root / "s1").mkdir(parents=True)
        (root / "s1" / "SKILL.md").write_text("# S1\nDesc", encoding="utf-8")
    (mod_root / "m1" / "skills" / "s2").mkdir(parents=True)
    (mod_root / "m1" / "skills" / "s2" / "SKILL.md").write_text("# S2\nDesc", encoding="utf-8")
    (mod_root / "m1" / "skills" / "s2" / "assets").mkdir(parents=True)
    (mod_root / "m1" / "skills" / "s2" / "assets" / "a.txt").write_text("a", encoding="utf-8")

    monkeypatch.setattr("democrai.core.platform.agents.skills.get_builtin_skills_dir", lambda: str(builtin))
    monkeypatch.setattr("democrai.core.platform.agents.skills.get_user_skills_dir", lambda: str(user))
    monkeypatch.setattr("democrai.core.platform.agents.skills.get_runtime_module_dirs", lambda: (str(mod_root),))
    monkeypatch.setattr("democrai.core.platform.agents.skills.app_ctx", lambda: SimpleNamespace(config=SimpleNamespace(get=lambda *_a, **_k: [])))

    loader = SkillLoader()
    discovered = loader.discover()
    assert discovered
    s2 = loader.get("s2")
    assert s2 is not None
    assert loader.list_assets(s2) == ["a.txt"]
    assert loader.resolve_asset(s2, "a.txt") is not None
    assert loader.resolve_asset(s2, "../x") is None
    assert loader.read_asset_text(s2, "a.txt") == "a"
    assert loader.match("s2 desc", limit=5)
    assert "<available_skills>" in loader.render_available_skills_xml()
    assert "<activated_skills>" in SkillLoader.render_activated_skills([s2])


def test_skill_script_access_allows_ready_file_read(tmp_path: Path):
    from democrai.core.platform.agents.models import SkillDefinition
    from democrai.core.platform.agents.models import SkillMetadata
    from democrai.core.platform.agents import skill_scripts

    skill_root = tmp_path / "skill"
    script_path = skill_root / "scripts" / "probe.py"
    ready_path = tmp_path / "ready" / "network.ready"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("print('ok')\n", encoding="utf-8")
    ready_path.parent.mkdir(parents=True)
    definition = SkillDefinition(
        metadata=SkillMetadata(
            name="system.unit_skill",
            description="unit",
            title="unit",
            script_paths=("probe.py",),
            module_name="system",
        ),
        content="unit",
        root_dir=skill_root,
    )

    access = skill_scripts._skill_script_access(definition, script_path, ready_path)
    resources = {
        (
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in access
    }

    assert ("read", str(ready_path.parent.resolve())) in resources
    assert ("create", str(ready_path.parent.resolve())) in resources
    assert ("modify", str(ready_path.parent.resolve())) in resources
    assert ("delete", str(ready_path.parent.resolve())) in resources


def test_skill_script_run_inherits_owner_module_access(monkeypatch, tmp_path: Path):
    from democrai.core.application.access_policy import AccessManifestRule
    from democrai.core.application.access_policy import AccessResource
    from democrai.core.application.access_policy import AccessSubject
    from democrai.core.platform.agents import skill_scripts
    from democrai.core.platform.agents.models import SkillDefinition
    from democrai.core.platform.agents.models import SkillMetadata

    skill_root = tmp_path / "skill"
    script_path = skill_root / "scripts" / "probe.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("print('ok')\n", encoding="utf-8")
    definition = SkillDefinition(
        metadata=SkillMetadata(
            name="system.unit_skill",
            description="unit",
            title="unit",
            script_paths=("probe.py",),
            module_name="system",
        ),
        content="unit",
        root_dir=skill_root,
    )

    owner_rule = AccessManifestRule(
        subject=AccessSubject.create("module", "system"),
        resource=AccessResource.create(
            resource_type="filesystem",
            operation="read",
            target="/srv/system/files",
        ),
    )
    monkeypatch.setattr(
        skill_scripts.OwnerModuleAccess,
        "resolve",
        classmethod(lambda cls: ("system", (owner_rule,))),
    )
    monkeypatch.setattr(skill_scripts, "_resolve_selected_skill", lambda name: definition)
    monkeypatch.setattr(skill_scripts, "_script_env", lambda: {})
    monkeypatch.setattr(
        skill_scripts, "_prepare_skill_script_network_policy", lambda *_a, **_k: ""
    )
    monkeypatch.setattr(
        skill_scripts, "_apply_skill_script_network_policy", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        skill_scripts, "_clear_skill_script_network_policy", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        skill_scripts, "_stop_skill_script_proxy_session", lambda *_a, **_k: None
    )

    captured_guard = {}

    class _Guard:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def _guard_context(**kwargs):
        captured_guard.update(kwargs)
        return _Guard()

    monkeypatch.setattr(skill_scripts, "process_guard_context", _guard_context)

    class _Proc:
        pid = 4321
        returncode = 0

        def communicate(self, timeout=None):
            return "ok", ""

        def poll(self):
            return 0

    monkeypatch.setattr(
        skill_scripts.subprocess, "Popen", lambda *_a, **_k: _Proc()
    )

    result = skill_scripts._run_skill_script_sync(
        skill="system.unit_skill",
        script="probe.py",
        args=(),
        timeout_seconds=5,
    )

    assert result["returncode"] == 0
    assert captured_guard["inherit_parent_access"] is False
    targets = {rule.resource.target for rule in captured_guard["access"]}
    assert "/srv/system/files" in targets
    assert str(script_path.resolve()) in targets


@pytest.mark.asyncio
async def test_agent_runtime_helpers_and_callable(monkeypatch):
    assert runtime_mod._merge_names(("a",), ("a", "b")) == ("a", "b")
    assert runtime_mod._resolve_pipeline_input(SimpleNamespace(input_template="{x}", input_key=None), {"x": 1}) == "1"
    assert runtime_mod._safe_format("{x}", {"x": "v"}) == "v"

    async def _fn(ctx=None, x=None):
        return {"ctx": ctx, "x": x}

    out = await runtime_mod._invoke_callable(
        _fn,
        payload={"x": 3},
        extra_context={"y": 1},
    )
    assert out["x"] == 3
    definition = AgentDefinition(name="a", description="d")
    assert runtime_mod._normalize_agent_run_result(definition, {"content": "c"}).content == "c"


@pytest.mark.asyncio
async def test_agent_runtime_tool_agent_and_pipeline(monkeypatch):
    _install_agent_runtime_stubs(monkeypatch)
    saved_tools = dict(agent_tool_registry._tools)
    records = []
    tool = AgentToolDefinition(
        name="echo",
        func=lambda input=None, **_k: {"echo": input},
        description="d",
        input_schema={"type": "object"},
    )
    definition = AgentDefinition(
        name="agent1",
        description="d",
        objective="chat",
        tools=("echo",),
        skills=(),
        max_iterations=2,
    )

    class _Provider:
        async def generate_completion(self, _messages, _opts):
            return SimpleNamespace(id="r1", content="done", tool_calls=[])

    try:
        agent_tool_registry.register(
            tool.name,
            tool.func,
            description=tool.description,
            input_schema=tool.input_schema,
        )
        runtime = runtime_mod.AgentRuntime(skill_loader=SkillLoader(skill_dirs=[]))
        runtime.agent_registry = {"agent1": definition}
        runtime.pipeline_registry = {
            "p1": PipelineDefinition(
                name="p1",
                description="d",
                steps=(PipelineStepDefinition(kind="tool", target="echo", output_key="out"),),
            )
        }

        assert (await runtime.run_tool("echo", arguments={"input": "x"}))["echo"] == "x"
        agent_result = await runtime.run_agent("agent1", input="hello", provider=_Provider())
        assert agent_result.content == "done"
        assert records == []
        pipeline_result = await runtime.run_pipeline("p1", input="i1")
        assert "out" in pipeline_result
    finally:
        agent_tool_registry._tools = saved_tools


@pytest.mark.asyncio
async def test_agent_runtime_tool_calls_parallel_and_listener(monkeypatch):
    _install_agent_runtime_stubs(monkeypatch)
    tool = AgentToolDefinition(
        name="ok",
        func=lambda **kwargs: {"ok": kwargs},
        description="d",
        input_schema={"type": "object"},
    )
    definition = AgentDefinition(
        name="agent2",
        description="d",
        objective="chat",
        tools=("ok",),
        skills=(),
        max_iterations=1,
    )

    class _Provider:
        async def generate_completion(self, _messages, _opts):
            return SimpleNamespace(id="r2", content="c", tool_calls=[])

    events = []
    runtime = runtime_mod.AgentRuntime(skill_loader=SkillLoader(skill_dirs=[]))
    runtime.agent_tool_registry = {"ok": tool}
    runtime.agent_registry = {"agent2": definition}
    result = await runtime.run_agent(
        "agent2",
        input="i",
        provider_override=_Provider(),
        listener=lambda event: events.append(event),
    )
    assert result.content == "c"
    assert any(event["type"] == "agent.run.finished" for event in events)
    assert current_agent_execution.get() is None

    pipeline_messages = []

    class _MessageProvider:
        async def generate_completion(self, _messages, _opts, *, on_message=None):
            if on_message is not None:
                value = on_message({"type": "agent.call", "name": "agent.child"})
                if hasattr(value, "__await__"):
                    await value
            return SimpleNamespace(id="r2m", content="cm", tool_calls=[])

    result_with_messages = await runtime.run_agent(
        "agent2",
        input="i",
        provider_override=_MessageProvider(),
        on_message=lambda message: pipeline_messages.append(message),
    )
    assert result_with_messages.content == "cm"
    assert pipeline_messages == [{"type": "agent.call", "name": "agent.child"}]

    inherited_pipeline_messages = []
    monkeypatch.setattr(
        "democrai.core.application.ai.pipeline_context._record_step",
        lambda *_a, **_k: None,
    )
    pipeline_context = create_ai_pipeline_context(
        root_method="agent_test",
        on_message=lambda message: inherited_pipeline_messages.append(message),
    )
    with ai_pipeline_context(pipeline_context):
        result_with_inherited_messages = await runtime.run_agent(
            "agent2",
            input="i",
            provider_override=_MessageProvider(),
        )
    assert result_with_inherited_messages.content == "cm"
    assert any(
        (
            message.get("type") == "agent.call"
            and message.get("name") == "agent.child"
        )
        if isinstance(message, dict)
        else (
            getattr(message, "type", "") == "agent.call"
            and getattr(message, "name", "") == "agent.child"
        )
        for message in inherited_pipeline_messages
    )

    child_events = []
    token = current_agent_execution.set(
        AgentExecutionContext(
            agent_name="parent",
            objective="chat",
            listener=lambda event: child_events.append(event),
        )
    )
    try:
        child_result = await runtime.run_agent(
            "agent2",
            input="child",
            provider_override=_Provider(),
        )
    finally:
        current_agent_execution.reset(token)
    assert child_result.content == "c"
    assert any(
        event["type"] == "agent.run.started" and event["agent_name"] == "agent2"
        for event in child_events
    )

    async def _run_tool(name, arguments=None, **_k):
        if name == "boom":
            raise RuntimeError("boom")
        return {"ok": name, "args": arguments}

    runtime.run_tool = _run_tool
    parallel_step = PipelineStepDefinition(
        kind="parallel",
        output_key="p",
        steps=(
            PipelineStepDefinition(kind="tool", target="ok", output_key="a"),
            PipelineStepDefinition(kind="tool", target="boom", output_key="b"),
        ),
        error_policy="collect_errors",
    )
    out = await runtime._execute_pipeline_step(
        parallel_step,
        state={"input": "x"},
        provider=None,
    )
    assert "p_errors" in out


@pytest.mark.asyncio
async def test_agent_runtime_passes_model_context_to_provider(monkeypatch):
    _install_agent_runtime_stubs(monkeypatch)
    captured = {}
    definition = AgentDefinition(
        name="agent3",
        description="desc",
        objective="chat",
        tools=("tool1",),
        skills=("skill1",),
        mcp_servers=("mcp1",),
        max_iterations=4,
    )

    class _Provider:
        async def generate_completion(self, messages, options):
            captured["messages"] = messages
            captured["options"] = options
            return SimpleNamespace(id="r3", content="ok", tool_calls=[])

    runtime = runtime_mod.AgentRuntime(skill_loader=SkillLoader(skill_dirs=[]))
    runtime.agent_registry = {"agent3": definition}
    result = await runtime.run_agent(
        "agent3",
        input="hello",
        provider=_Provider(),
        extra_tools=("tool2",),
        extra_skills=("skill2",),
    )
    assert result.content == "ok"
    assert [message.role.value for message in captured["messages"]] == ["system", "user"]
    assert captured["options"] == {
        "tools": ["tool1", "tool2"],
        "skills": ["skill1", "skill2"],
        "mcp": ["mcp1"],
        "agents": [],
        "tool_max_iterations": 4,
    }
