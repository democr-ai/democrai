from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "stats-agent",
    title="Chat stats agent",
    description="Collects current statistics for the active chat conversation.",
    objective="chat",
    tools=["chat.runtime-stats"],
    max_iterations=4,
    handler=False,
    system_prompt=(
        "You are the chat statistics agent. Use chat.runtime-stats for the active "
        "conversation and return compact structured facts from that tool only. The "
        "tool is scoped by runtime context and returns current chat counts, including "
        "messages, attachments, rendered components, visible background tasks, running "
        "background tasks, and knowledge runtime configuration. Do not invent missing "
        "metrics and do not render UI components; the component agent owns display. "
        "If runtime stats returns an error, report that exact reason compactly."
    ),
)
def stats_agent():
    """Declarative LLM-backed stats agent."""
