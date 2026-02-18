"""Event handler — reacts to system events.

This handler is invoked when specific events are published
on the OmniBrain event bus (e.g., new_email, calendar_update).
"""

from __future__ import annotations

from typing import Any


async def handle(context: Any, event: dict[str, Any]) -> dict[str, Any]:
    """Handle a system event.

    Args:
        context: SkillContext with access to memory, notifications, and LLM.
        event: Event data dict with at least "type" and "data" keys.

    Returns:
        Dict with results.
    """
    event_type = event.get("type", "unknown")

    # Example: react to specific events
    # if event_type == "new_email":
    #     sender = event["data"].get("from", "")
    #     context.notify(f"New email from {sender}")

    return {
        "status": "handled",
        "event_type": event_type,
    }
