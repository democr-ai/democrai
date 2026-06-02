from types import SimpleNamespace

import pytest

import democrai.sdk.ai as sdk_ai_mod


@pytest.mark.asyncio
async def test_ai_provider_resolution(monkeypatch):
    monkeypatch.setenv("DEMOCRAI_ENGINE_ORCHESTRATOR", "1")
    async def _get_provider_for_objective(*_a, **_k):
        return {"status": "ok", "provider": "objective-provider"}

    async def _get_provider_by_model_registry_id(*_a, **_k):
        return {"status": "ok", "provider": "model-provider"}

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(
            model_orchestrator=SimpleNamespace(
                get_provider_for_objective=_get_provider_for_objective,
                get_provider_by_model_registry_id=_get_provider_by_model_registry_id,
            )
        ),
    )

    ai = sdk_ai_mod.AI(SimpleNamespace(module_name="mod", session={}))
    assert (await ai.get_provider_for_objective("chat"))["provider"] == "objective-provider"
    assert (
        await ai.get_provider_by_model_registry_id(1, confirm_swap=True)
    )["provider"] == "model-provider"


@pytest.mark.asyncio
async def test_ai_runtime_discovery_and_execution(monkeypatch):
    tool = SimpleNamespace(name="t1", user_selectable=True)
    agent = SimpleNamespace(name="a1")
    pipeline = SimpleNamespace(name="p1")
    mcp_server = SimpleNamespace(id=1, name="mcp1")
    skill = SimpleNamespace(metadata=SimpleNamespace(name="s1"))
    tool_registry = SimpleNamespace(
        get_all=lambda module_name=None: [tool],
        get=lambda name: tool if name == "t1" else None,
    )
    agent_registry = SimpleNamespace(
        get_all=lambda module_name=None: [agent],
        get=lambda name: agent if name == "a1" else None,
    )
    pipeline_registry = SimpleNamespace(
        get_all=lambda module_name=None: [pipeline],
        get=lambda name: pipeline if name == "p1" else None,
    )
    skill_registry = SimpleNamespace(get_all=lambda module_name=None: [skill])
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.agents.registry",
        SimpleNamespace(
            agent_tool_registry=tool_registry,
            agent_registry=agent_registry,
            pipeline_registry=pipeline_registry,
            skill_registry=skill_registry,
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.mcp.registry",
        SimpleNamespace(
            list_servers=lambda enabled_only=True: [mcp_server]
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.agents.runtime",
        SimpleNamespace(
            agent_runtime=SimpleNamespace(
                run_tool=lambda *a, **k: __import__("asyncio").sleep(
                    0, result={"tool": "ok"}
                ),
                run_agent=lambda *a, **k: __import__("asyncio").sleep(
                    0, result={"agent": "ok"}
                ),
                run_pipeline=lambda *a, **k: __import__("asyncio").sleep(
                    0, result={"pipeline": "ok"}
                ),
            )
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.agents.skills",
        SimpleNamespace(
            SkillLoader=lambda: SimpleNamespace(
                discover=lambda: [SimpleNamespace(metadata=SimpleNamespace(name="s1"))]
            )
        ),
    )

    ai = sdk_ai_mod.AI(SimpleNamespace(module_name="mod", session={}))
    assert ai.list_tools() == [tool]
    assert ai.get_tool("t1") is tool
    assert ai.list_agents() == [agent]
    assert ai.get_agent("a1") is agent
    assert ai.list_pipelines() == [pipeline]
    assert ai.get_pipeline("p1") is pipeline
    assert ai.list_mcp_servers() == [mcp_server]
    assert ai.list_skills()[0].metadata.name == "s1"
    assert ai.list_skills(["s1"])[0].metadata.name == "s1"
    assert (await ai.run_tool("t1")) == {"tool": "ok"}
    assert (await ai.run_agent("a1")) == {"agent": "ok"}
    assert (await ai.run_pipeline("p1")) == {"pipeline": "ok"}

    with pytest.raises(ValueError):
        await ai.run_tool("missing")
    with pytest.raises(ValueError):
        await ai.run_agent("missing")
    with pytest.raises(ValueError):
        await ai.run_pipeline("missing")


def test_ai_mcp_servers_use_runtime_registry(monkeypatch):
    mcp_servers = [
        SimpleNamespace(id=1, name="mcp1"),
        SimpleNamespace(id=2, name="mcp2"),
    ]
    calls = []

    def _list_servers(*, enabled_only=True):
        calls.append(enabled_only)
        return [mcp_servers[1]]

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.mcp.registry",
        SimpleNamespace(list_servers=_list_servers),
    )
    sdk = SimpleNamespace(module_name="mod", session={})

    assert sdk_ai_mod.AI(sdk).list_mcp_servers() == [mcp_servers[1]]
    assert calls == [True]
