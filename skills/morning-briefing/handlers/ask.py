"""Morning Briefing — Ask handler.

Returns the latest briefing or generates one on demand.
"""

from __future__ import annotations


async def handle(ctx, query: str) -> dict:
    """Return the latest briefing text.

    If the user asks for a specific type (morning/evening), serve that.
    Otherwise, return the most recent one.
    """
    q = query.lower()

    # Determine which briefing to serve
    if "evening" in q:
        briefing_type = "evening"
    else:
        briefing_type = "morning"

    # Try skill-local storage first (most recent)
    text = await ctx.get_data(f"last_{briefing_type}_text")
    date = await ctx.get_data(f"last_{briefing_type}_date")

    if text:
        return {
            "answer": text,
            "type": briefing_type,
            "date": date or "unknown",
            "source": "cached",
        }

    # Fallback: search memory for stored briefings
    results = await ctx.memory_search(
        f"{briefing_type} briefing",
        limit=3,
        source="skill:morning-briefing",
    )

    if results:
        latest = results[0]
        return {
            "answer": latest.get("text", "No briefing text available."),
            "type": briefing_type,
            "date": latest.get("metadata", {}).get("date", "unknown"),
            "source": "memory",
        }

    return {
        "answer": (
            f"No {briefing_type} briefing found yet. "
            f"Briefings are generated automatically — one should appear soon."
        ),
        "type": briefing_type,
        "source": "none",
    }
