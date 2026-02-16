"""Calendar Assistant — Event handler.

Called when an ``event_approaching`` event fires (≤30 min to meeting).
Sends a meeting brief notification with context about attendees.
"""

from __future__ import annotations


async def handle(ctx, event: dict) -> dict:
    """Prepare and send a meeting brief notification.

    *event* keys: ``title``, ``start``, ``minutes_until``, ``attendees``, ``event_id``.

    Returns ``{"briefed": bool, "attendee_context": list}``.
    """
    title = event.get("title", "Unknown meeting")
    minutes_until = event.get("minutes_until", 0)
    attendees = event.get("attendees", [])

    # 1. Gather context about attendees from memory
    attendee_context = []
    for attendee in attendees[:5]:
        results = await ctx.memory_search(str(attendee), limit=3)
        if results:
            latest = results[0].get("text", "")[:150]
            attendee_context.append({
                "name": str(attendee),
                "context": latest,
            })

    # 2. Compose brief
    brief_lines = [f"📅 Meeting in {minutes_until} minutes: {title}"]

    if attendee_context:
        brief_lines.append("Attendee context:")
        for ac in attendee_context:
            brief_lines.append(f"  • {ac['name']}: {ac['context']}")

    if not attendee_context and attendees:
        brief_lines.append(f"Attendees: {', '.join(str(a) for a in attendees[:5])}")

    brief_text = "\n".join(brief_lines)

    # 3. Notify the user
    level = "important" if minutes_until <= 10 else "fyi"
    await ctx.notify(brief_text, level=level)

    ctx.log(f"Meeting brief sent: {title} in {minutes_until}m ({len(attendee_context)} context)")

    return {
        "briefed": True,
        "title": title,
        "minutes_until": minutes_until,
        "attendee_context": attendee_context,
    }
