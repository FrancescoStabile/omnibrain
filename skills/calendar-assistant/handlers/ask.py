"""Calendar Assistant — Ask handler.

Called when the user asks about their schedule, meetings, or events.
Searches memory for calendar data and formats a helpful response.
"""

from __future__ import annotations


async def handle(ctx, query: str) -> dict:
    """Answer questions about the user's calendar and schedule.

    Returns ``{"answer": str, "events": list[dict]}``.
    """
    # 1. Search memory for calendar-related entries
    results = await ctx.memory_search(query, limit=10, source="skill:calendar-assistant")

    if not results:
        results = await ctx.memory_search(query, limit=10)

    # Filter to calendar-related results
    calendar_results = [
        r for r in results
        if "calendar" in r.get("source", "") or "event" in r.get("text", "").lower()
    ]

    if not calendar_results:
        calendar_results = results

    if not calendar_results:
        return {"answer": "I don't have any calendar information matching your query.", "events": []}

    # 2. Try LLM-composed answer
    if ctx.has_permission("llm_access") and calendar_results:
        context_block = "\n---\n".join(
            r.get("text", "")[:300] for r in calendar_results[:5]
        )
        prompt = (
            f"Based on the user's calendar data, answer: {query}\n\n"
            f"Calendar data:\n{context_block}\n\n"
            "Be concise. Mention times, attendees, and locations."
        )
        try:
            answer = await ctx.llm_complete(prompt, task_type="quick")
            if answer:
                return {"answer": answer, "events": calendar_results[:5]}
        except Exception:
            pass

    # 3. Manual formatting fallback
    lines = [f"Found {len(calendar_results)} calendar event(s):"]
    for r in calendar_results[:5]:
        text = r.get("text", "")[:200]
        lines.append(f"  • {text}")

    return {
        "answer": "\n".join(lines),
        "events": calendar_results[:5],
    }
