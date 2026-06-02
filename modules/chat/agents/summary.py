from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "summary-agent",
    title="Chat summary agent",
    description="Maintains compact summaries for long chat threads.",
    objective="chat",
    max_iterations=2,
    handler=False,
    system_prompt=(
        "Summarize the chat thread state for future context. Preserve user goals, "
        "decisions, attachments, tool results, unresolved questions, and next steps. "
        "Be compact and factual."
    ),
)
def summary_agent():
    """Declarative LLM-backed summary agent."""
