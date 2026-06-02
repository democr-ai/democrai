from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "test-agent",
    title="Test agent",
    description="Deterministic test agent for multi-agent engine flow checks.",
    objective="chat",
)
def test_agent(input: str = "") -> dict[str, str]:
    return {
        "content": f"system_test_agent: {input}",
    }
