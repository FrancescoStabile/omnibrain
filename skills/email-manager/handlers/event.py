"""Email Manager — Event handler.

Called when a ``new_email`` event is emitted (by the poll handler
or any other source). Performs real-time triage and notification.
"""

from __future__ import annotations


async def handle(ctx, event: dict) -> dict:
    """Process a new email event — classify and notify if urgent.

    *event* keys: ``sender``, ``subject``, ``is_urgent``, ``is_unread``.

    Returns ``{"action": str, "notified": bool}``.
    """
    sender = event.get("sender", "unknown")
    subject = event.get("subject", "(no subject)")
    is_urgent = event.get("is_urgent", False)
    is_unread = event.get("is_unread", True)

    action = "none"
    notified = False

    # 1. Urgent emails → immediate notification
    if is_urgent and is_unread:
        await ctx.notify(
            f"📧 Urgent email from {sender}: {subject}",
            level="important",
        )
        action = "notified_urgent"
        notified = True

    # 2. Known contact → FYI notification
    elif is_unread:
        contacts = await ctx.get_contacts(sender)
        if contacts:
            contact_name = contacts[0].get("name", sender)
            await ctx.notify(
                f"📧 New email from {contact_name}: {subject}",
                level="fyi",
            )
            action = "notified_known_contact"
            notified = True
        else:
            action = "skipped_unknown_sender"

    ctx.log(f"Event processed: {sender} / {subject} → {action}")
    return {"action": action, "notified": notified}
