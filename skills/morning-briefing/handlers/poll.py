"""Morning Briefing — Schedule handler (poll.py).

Generates a personalized daily briefing by collecting data from memory,
calendar, email, and proposals, then composing a summary.
"""

from __future__ import annotations

from datetime import datetime


async def handle(ctx) -> dict:
    """Generate the morning (or evening) briefing.

    Flow:
        1. Determine briefing type from time of day
        2. Collect recent memory entries (emails, events, patterns)
        3. Get pending proposals count
        4. Compose briefing via LLM or manual formatting
        5. Store briefing text in skill data
        6. Notify user that briefing is ready
    """
    now = datetime.now()
    hour = now.hour
    briefing_type = "morning" if hour < 14 else "evening"
    date_str = now.strftime("%Y-%m-%d")

    # Check if we already generated one today
    last_date = await ctx.get_data(f"last_{briefing_type}_date")
    if last_date == date_str:
        return {"status": "already_generated", "type": briefing_type, "date": date_str}

    # Collect data from memory
    recent_emails = await ctx.memory_search("email", limit=10, source="skill:email-manager")
    recent_events = await ctx.memory_search("meeting OR event OR calendar", limit=10)
    recent_all = await ctx.memory_search("", limit=20)

    # Gather section data
    sections = {
        "type": briefing_type,
        "date": date_str,
        "greeting": _greeting(ctx.user_name, hour),
        "email_count": len(recent_emails),
        "event_count": len(recent_events),
        "total_memory": len(recent_all),
    }

    # Compose briefing
    if ctx.has_permission("llm_access"):
        context = _build_context(recent_emails, recent_events, recent_all)
        prompt = (
            f"Generate a concise {briefing_type} briefing for {ctx.user_name}.\n\n"
            f"Today is {now.strftime('%A, %B %d, %Y')}.\n\n"
            f"Recent activity:\n{context}\n\n"
            f"Write a warm, helpful summary in 3-5 short sections. "
            f"Include: overnight highlights, what needs attention, and today's schedule. "
            f"Be specific — reference actual names, subjects, and details from the data."
        )
        briefing_text = await ctx.llm_complete(prompt, task_type="reasoning")
    else:
        briefing_text = _manual_briefing(sections, recent_emails, recent_events)

    if not briefing_text:
        briefing_text = _manual_briefing(sections, recent_emails, recent_events)

    # Store the briefing
    await ctx.set_data(f"last_{briefing_type}_date", date_str)
    await ctx.set_data(f"last_{briefing_type}_text", briefing_text)

    # Store in memory for future reference
    await ctx.memory_store(
        content=f"{briefing_type.title()} briefing — {date_str}\n\n{briefing_text}",
        metadata={"type": f"{briefing_type}_briefing", "date": date_str},
    )

    # Notify user
    await ctx.notify(
        f"Your {briefing_type} briefing is ready! {sections['email_count']} emails, "
        f"{sections['event_count']} events tracked.",
        level="important",
    )

    return {
        "status": "generated",
        "type": briefing_type,
        "date": date_str,
        "email_count": sections["email_count"],
        "event_count": sections["event_count"],
        "text_length": len(briefing_text),
    }


def _greeting(user_name: str, hour: int) -> str:
    if hour < 12:
        return f"Good morning, {user_name}."
    if hour < 18:
        return f"Good afternoon, {user_name}."
    return f"Good evening, {user_name}."


def _build_context(emails: list, events: list, all_items: list) -> str:
    parts = []
    if emails:
        parts.append("## Recent Emails")
        for e in emails[:5]:
            parts.append(f"- {e.get('text', '')[:200]}")
    if events:
        parts.append("\n## Calendar / Events")
        for e in events[:5]:
            parts.append(f"- {e.get('text', '')[:200]}")
    if all_items:
        parts.append(f"\n## Other Activity ({len(all_items)} items)")
        for item in all_items[:5]:
            if item not in emails and item not in events:
                parts.append(f"- {item.get('text', '')[:150]}")
    return "\n".join(parts) if parts else "No recent activity found."


def _manual_briefing(sections: dict, emails: list, events: list) -> str:
    lines = [sections["greeting"], ""]

    if sections["email_count"] > 0:
        lines.append(f"**Email:** {sections['email_count']} recent emails in memory.")
        for e in emails[:3]:
            lines.append(f"  - {e.get('text', '')[:120]}")
        lines.append("")

    if sections["event_count"] > 0:
        lines.append(f"**Schedule:** {sections['event_count']} events tracked.")
        for e in events[:3]:
            lines.append(f"  - {e.get('text', '')[:120]}")
        lines.append("")

    if sections["email_count"] == 0 and sections["event_count"] == 0:
        lines.append("All quiet — no recent activity to report. Enjoy the calm.")

    return "\n".join(lines)
