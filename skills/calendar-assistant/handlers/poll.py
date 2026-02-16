"""Calendar Assistant — Schedule handler.

Called every 15 minutes to sync calendar events, detect conflicts,
and emit ``event_approaching`` events for upcoming meetings.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


async def handle(ctx) -> dict:
    """Sync calendar, detect conflicts, prepare meeting alerts.

    Returns ``{synced, conflicts, approaching}``.
    """
    # 1. Get Calendar client
    cal = ctx.get_integration("calendar")
    if cal is None:
        ctx.log("Calendar not authenticated — skipping sync", level="warning")
        return {"synced": 0, "error": "calendar_auth_failed"}

    # 2. Fetch today's events
    try:
        events = cal.get_today_events()
    except Exception as exc:
        ctx.log(f"Calendar fetch failed: {exc}", level="error")
        return {"synced": 0, "error": str(exc)}

    # 3. Also fetch upcoming (next 3 days)
    try:
        upcoming = cal.get_upcoming_events(days=3)
    except Exception:
        upcoming = []

    all_events = events + [e for e in upcoming if e not in events]

    # 4. Store events in memory
    stored = 0
    for ev in all_events:
        title = getattr(ev, "title", "")
        start = getattr(ev, "start_time", "")
        location = getattr(ev, "location", "")
        attendees = getattr(ev, "attendees", [])
        duration = getattr(ev, "duration_minutes", 0)

        start_str = start.isoformat() if isinstance(start, datetime) else str(start)
        attendee_names = ", ".join(str(a) for a in attendees[:5]) if attendees else "none"

        content = (
            f"Calendar event: {title}\n"
            f"When: {start_str}\n"
            f"Duration: {duration}m\n"
            f"Location: {location or 'none'}\n"
            f"Attendees: {attendee_names}"
        )
        await ctx.memory_store(content, {
            "type": "calendar_event",
            "title": title,
            "start": start_str,
            "duration_minutes": duration,
            "event_id": getattr(ev, "id", ""),
        })
        stored += 1

    # 5. Detect conflicts (overlapping events)
    conflict_count = 0
    sorted_events = sorted(events, key=lambda e: getattr(e, "start_time", datetime.min))

    for i in range(len(sorted_events) - 1):
        ev_a = sorted_events[i]
        ev_b = sorted_events[i + 1]

        a_start = getattr(ev_a, "start_time", None)
        a_dur = getattr(ev_a, "duration_minutes", 0) or 0
        b_start = getattr(ev_b, "start_time", None)

        if a_start and b_start and isinstance(a_start, datetime) and isinstance(b_start, datetime):
            a_end = a_start + timedelta(minutes=a_dur)
            if a_end > b_start:
                conflict_count += 1
                await ctx.notify(
                    f"⚠️ Schedule conflict: '{getattr(ev_a, 'title', '')}' "
                    f"overlaps with '{getattr(ev_b, 'title', '')}'",
                    level="important",
                )

    # 6. Check for approaching events (within 30 minutes)
    approaching = 0
    now = datetime.now(timezone.utc)
    brief_window = timedelta(minutes=30)

    notified_ids = set()
    notified_raw = await ctx.get_data("notified_event_ids", "")
    if notified_raw and isinstance(notified_raw, str):
        notified_ids = set(notified_raw.split(","))

    for ev in events:
        ev_start = getattr(ev, "start_time", None)
        ev_id = str(getattr(ev, "id", ""))

        if ev_start and isinstance(ev_start, datetime):
            time_until = ev_start - now
            if timedelta(0) < time_until <= brief_window and ev_id not in notified_ids:
                approaching += 1
                notified_ids.add(ev_id)
                await ctx.emit_event("event_approaching", {
                    "title": getattr(ev, "title", ""),
                    "start": ev_start.isoformat(),
                    "minutes_until": int(time_until.total_seconds() / 60),
                    "attendees": [str(a) for a in getattr(ev, "attendees", [])[:5]],
                    "event_id": ev_id,
                })

    # Save notified IDs (keep last 50 to prevent unbounded growth)
    trimmed = sorted(notified_ids)[-50:]
    await ctx.set_data("notified_event_ids", ",".join(trimmed))

    summary = {
        "synced": stored,
        "today_events": len(events),
        "upcoming_events": len(upcoming),
        "conflicts": conflict_count,
        "approaching": approaching,
    }

    if events:
        ctx.log(f"Synced {len(events)} today events, {conflict_count} conflicts")

    return summary
