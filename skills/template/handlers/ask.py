"""Ask handler — responds to user questions.

This handler is invoked when the user asks something that matches
your skill's on_ask trigger pattern.
"""

from __future__ import annotations

from typing import Any


async def handle(context: Any, query: str) -> dict[str, Any]:
    """Handle a user question.

    Args:
        context: SkillContext with access to memory, notifications, and LLM.
        query: The user's question text.

    Returns:
        Dict with "response" key containing the answer text.
    """
    # Example: use LLM to generate a response
    # answer = await context.llm(f"Answer this question: {query}")

    return {
        "response": f"You asked about: {query}",
    }
