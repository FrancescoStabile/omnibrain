"""Email Manager — Schedule handler.

Called every N minutes to poll for new emails.
Uses ``ctx.get_integration("gmail")`` to access the GmailClient
through the Skill Protocol sandbox.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


async def handle(ctx) -> dict:
    """Poll Gmail for new emails, triage, and store in memory.

    Returns a summary dict: ``{fetched, stored, urgent, proposed}``.
    """
    # 1. Resolve Gmail client (permission-guarded)
    gmail = ctx.get_integration("gmail")
    if gmail is None:
        ctx.log("Gmail not authenticated — skipping poll", level="warning")
        return {"fetched": 0, "error": "gmail_auth_failed"}

    # 2. Determine time window
    last_poll_iso = await ctx.get_data("last_poll_ts")
    try:
        max_fetch = int(await ctx.get_data("max_fetch", 20))
    except (TypeError, ValueError):
        max_fetch = 20

    try:
        emails = gmail.fetch_recent(max_results=max_fetch)
    except Exception as exc:
        ctx.log(f"Gmail fetch failed: {exc}", level="error")
        return {"fetched": 0, "error": str(exc)}

    if not emails:
        await ctx.set_data("last_poll_ts", datetime.now(timezone.utc).isoformat())
        return {"fetched": 0, "stored": 0, "urgent": 0, "proposed": 0}

    # 3. Filter new emails since last poll
    if last_poll_iso:
        try:
            last_poll_dt = datetime.fromisoformat(last_poll_iso)
        except ValueError:
            last_poll_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        last_poll_dt = datetime.now(timezone.utc) - timedelta(hours=24)

    new_emails = []
    for em in emails:
        em_date = getattr(em, "date", None)
        if em_date and isinstance(em_date, datetime):
            if em_date > last_poll_dt:
                new_emails.append(em)
        else:
            new_emails.append(em)

    # 4. Store each new email in memory + emit event
    stored = 0
    urgent_count = 0
    proposed = 0

    for em in new_emails:
        subject = getattr(em, "subject", "")
        sender = getattr(em, "sender", "")
        snippet = getattr(em, "snippet", "") or getattr(em, "body", "")[:200]
        is_unread = getattr(em, "is_unread", True)

        # Store in memory
        content = f"Email from {sender}: {subject}\n{snippet}"
        metadata = {
            "type": "email",
            "sender": sender,
            "subject": subject,
            "is_unread": is_unread,
            "message_id": getattr(em, "id", ""),
        }
        await ctx.memory_store(content, metadata)
        stored += 1

        # Classify urgency (simple heuristic)
        urgent_keywords = {"urgent", "asap", "critical", "deadline", "important"}
        is_urgent = any(kw in subject.lower() for kw in urgent_keywords)

        if is_urgent:
            urgent_count += 1

        # Emit event for other skills
        await ctx.emit_event("new_email", {
            "sender": sender,
            "subject": subject,
            "is_urgent": is_urgent,
            "is_unread": is_unread,
        })

        # Propose action for urgent emails
        if is_urgent and is_unread:
            await ctx.propose_action(
                type="reply_email",
                title=f"Reply to urgent email from {sender}",
                description=f"Subject: {subject}\n{snippet[:100]}",
                action_data={"message_id": getattr(em, "id", ""), "sender": sender},
                priority=4,
            )
            proposed += 1

    # 5. Update last poll timestamp
    await ctx.set_data("last_poll_ts", datetime.now(timezone.utc).isoformat())

    summary = {
        "fetched": len(emails),
        "new": len(new_emails),
        "stored": stored,
        "urgent": urgent_count,
        "proposed": proposed,
    }

    if new_emails:
        ctx.log(f"Polled {len(new_emails)} new emails ({urgent_count} urgent)")

    return summary
