from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "planner",
    title="Task planner",
    description="Breaks a request into a small executable plan and delegates summarization when useful.",
    objective="chat",
    system_prompt=(
        "You are a pragmatic task planner. Produce short, ordered steps that can be "
        "executed and verified. Use the summarizer subagent when the request contains "
        "long context, multiple goals, or unclear constraints. Keep base configuration "
        "and user-selected extensions in mind, and call out risky assumptions."
    ),
    tools=["agent.system.summarizer"],
    max_iterations=4,
    handler=False,
)
def planner_agent():
    """Declarative LLM-backed agent."""
