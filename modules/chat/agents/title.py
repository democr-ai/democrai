from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "title-agent",
    title="Chat title agent",
    description="Creates short titles for new chat threads.",
    objective="chat",
    max_iterations=1,
    handler=False,
    system_prompt=(
        "Generate a short chat thread title from the first user message. "
        "Return only the title, no punctuation wrapper, maximum six words."
    ),
)
def title_agent():
    """Declarative LLM-backed title agent."""
