"""Poll handler — runs on a schedule.

This handler is invoked periodically based on your skill.yaml trigger.
Use it for background data collection, monitoring, or periodic tasks.
"""

from __future__ import annotations

from typing import Any


async def handle(context: Any) -> dict[str, Any]:
    """Scheduled poll handler.

    Args:
        context: SkillContext with access to memory, notifications, and LLM.

    Returns:
        Dict with results. Include "notify" key to send a notification.
    """
    # Example: check something and notify if interesting
    # data = await context.llm("Summarize the latest news about AI")

    return {
        "status": "ok",
        "message": "Poll completed",
        # "notify": "Something interesting happened!",
    }
