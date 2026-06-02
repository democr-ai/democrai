from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "summarizer",
    title="Summarizer",
    description="Condenses long or messy input into a concise operational summary.",
    objective="chat",
    system_prompt=(
        "You are a concise operational summarizer. Turn the user input into a compact "
        "summary with: main request, known facts, assumptions, missing information, and "
        "next actions. Do not invent facts. If information is ambiguous, say exactly what "
        "is ambiguous."
    ),
    max_iterations=2,
    handler=False,
)
def summarizer_agent():
    """Declarative LLM-backed agent."""
