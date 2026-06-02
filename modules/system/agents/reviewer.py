from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "reviewer",
    title="Reviewer",
    description="Reviews answers or plans for gaps, risks, and missing verification.",
    objective="chat",
    system_prompt=(
        "You are a direct reviewer. Inspect the provided answer, plan, or result for "
        "incorrect assumptions, missing checks, unclear ownership, and incomplete next "
        "steps. Use the planner subagent when the input needs to be turned into a clearer "
        "execution plan. Use the summarizer subagent when the input is long. Return the "
        "highest-impact findings first, then a compact revised recommendation."
    ),
    tools=["agent.system.summarizer", "agent.system.planner"],
    max_iterations=5,
    handler=False,
)
def reviewer_agent():
    """Declarative LLM-backed agent."""
