"""
OmniBrain — Extractors Registry

Maps tool names to extractor functions. Extractors process raw tool output
into structured domain data (contacts, events, observations) and store
it in the database.

This follows Omnigent's EXTRACTORS pattern from manifesto Section 9:
    EXTRACTORS["fetch_emails"] = lambda profile, result, args: extract_emails(...)
    EXTRACTORS["classify_email"] = lambda profile, result, args: extract_classification(...)
    EXTRACTORS["get_today_events"] = lambda profile, result, args: extract_calendar(...)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from omnibrain.models import ContactInfo, EmailMessage, EventSource

logger = logging.getLogger("omnibrain.extractors")

# Type for extractor functions
ExtractorFn = Callable[[Any, dict[str, Any], dict[str, Any]], dict[str, Any]]

# Global extractors registry
EXTRACTORS: dict[str, ExtractorFn] = {}


# ═══════════════════════════════════════════════════════════════════════════
# Email Extractors
# ═══════════════════════════════════════════════════════════════════════════


def extract_emails(
    profile: Any,
    result: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured data from fetch_emails result.

    Takes the raw fetch_emails output and creates:
    - ContactInfo objects for each unique sender
    - Event entries for storage in DB
    - Summary statistics for the agent

    Args:
        profile: The OmniBrainProfile (or Any domain profile).
        result: The dict returned by fetch_emails tool.
        args: The original tool arguments.

    Returns:
        Dict with extracted contacts, event summaries, and stats.
    """
    emails = result.get("emails", [])
    if not emails:
        return {"contacts": [], "summaries": [], "stats": {"total": 0}}

    contacts: dict[str, ContactInfo] = {}
    summaries: list[dict[str, Any]] = []

    for email_data in emails:
        sender_email = email_data.get("sender_email", "")
        sender_name = email_data.get("sender_name", "")

        # Build/update contact
        if sender_email and sender_email not in contacts:
            contacts[sender_email] = ContactInfo(
                email=sender_email,
                name=sender_name,
            )

        # Build summary for agent reasoning
        summaries.append({
            "id": email_data.get("id", ""),
            "from": f"{sender_name} <{sender_email}>" if sender_name else sender_email,
            "subject": email_data.get("subject", ""),
            "date": email_data.get("date", ""),
            "is_read": email_data.get("is_read", True),
            "has_attachments": email_data.get("has_attachments", False),
            "preview": email_data.get("body_preview", "")[:200],
        })

    # Stats
    unread_count = sum(1 for e in emails if not e.get("is_read", True))
    with_attachments = sum(1 for e in emails if e.get("has_attachments", False))

    stats = {
        "total": len(emails),
        "unread": unread_count,
        "with_attachments": with_attachments,
        "unique_senders": len(contacts),
    }

    logger.info(
        f"Extracted {len(emails)} emails: {unread_count} unread, "
        f"{len(contacts)} unique senders"
    )

    return {
        "contacts": [c.to_dict() for c in contacts.values()],
        "summaries": summaries,
        "stats": stats,
    }


def extract_classification(
    profile: Any,
    result: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured data from classify_email result.

    Updates email priority and creates action proposals if needed.

    Returns:
        Dict with classification details and any proposed actions.
    """
    urgency = result.get("urgency", "medium")
    category = result.get("category", "fyi")
    action = result.get("action", "archive")
    draft_needed = result.get("draft_needed", False)

    proposed_actions = []

    if draft_needed:
        proposed_actions.append({
            "type": "email_draft",
            "title": f"Draft response to email {args.get('email_id', '?')}",
            "description": f"Email classified as {urgency}/{category}. Action: {action}.",
            "priority": {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(urgency, 2),
        })

    return {
        "classification": result,
        "proposed_actions": proposed_actions,
        "requires_attention": urgency in ("critical", "high"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Calendar Extractors (stub — Phase 1 Day 5-6)
# ═══════════════════════════════════════════════════════════════════════════


def extract_calendar(
    profile: Any,
    result: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured data from calendar tool results.

    Processes get_today_events / get_upcoming_events output and creates:
    - Event summaries for the agent
    - Meeting stats (total time, attendee counts)
    - Upcoming conflict detection
    """
    events = result.get("events", [])
    if not events:
        return {"events": [], "stats": {"total": 0, "total_minutes": 0}}

    # Build stats
    total_minutes = sum(e.get("duration_minutes", 0) for e in events)
    with_attendees = sum(1 for e in events if e.get("attendees"))
    recurring = sum(1 for e in events if e.get("is_recurring"))

    # Collect unique attendees across all events
    all_attendees: set[str] = set()
    for event in events:
        for attendee in event.get("attendees", []):
            all_attendees.add(attendee)

    stats = {
        "total": len(events),
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 1),
        "with_attendees": with_attendees,
        "recurring": recurring,
        "unique_attendees": len(all_attendees),
    }

    logger.info(
        f"Extracted {len(events)} calendar events: "
        f"{total_minutes}min total, {len(all_attendees)} unique attendees"
    )

    return {
        "events": events,
        "stats": stats,
        "summary": result.get("summary", ""),
    }


def extract_memory_results(
    profile: Any,
    result: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured data from search_memory result.

    Processes memory search results for agent reasoning:
    - Groups results by source_type
    - Extracts unique contacts mentioned
    - Summarizes relevance scores

    Args:
        profile: The OmniBrainProfile (or Any domain profile).
        result: The dict returned by search_memory tool.
        args: The original tool arguments.

    Returns:
        Dict with organized results, contacts, and stats.
    """
    results = result.get("results", [])
    count = result.get("count", 0)

    if not results:
        return {"results": [], "count": 0, "contacts": [], "by_source": {}}

    # Group by source type
    by_source: dict[str, list[dict[str, Any]]] = {}
    all_contacts: set[str] = set()

    for item in results:
        source_type = item.get("source_type", "unknown")
        if source_type not in by_source:
            by_source[source_type] = []
        by_source[source_type].append(item)

        for contact in item.get("contacts", []):
            all_contacts.add(contact)

    # Compute average score
    scores = [item.get("score", 0) for item in results]
    avg_score = sum(scores) / len(scores) if scores else 0

    logger.info(
        f"Extracted {count} memory results: "
        f"{', '.join(f'{k}={len(v)}' for k, v in by_source.items())}"
    )

    return {
        "results": results,
        "count": count,
        "contacts": sorted(all_contacts),
        "by_source": {k: len(v) for k, v in by_source.items()},
        "avg_score": round(avg_score, 4),
        "query": result.get("query", args.get("query", "")),
        "backend": result.get("backend", "unknown"),
    }


def extract_observation(
    profile: Any,
    result: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured data from store_observation result.

    Returns:
        Dict with stored observation confirmation.
    """
    return {
        "stored": result.get("stored", False),
        "pattern_type": result.get("pattern_type", ""),
        "confidence": result.get("confidence", 0),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Register all extractors
# ═══════════════════════════════════════════════════════════════════════════

EXTRACTORS["fetch_emails"] = extract_emails
EXTRACTORS["search_emails"] = extract_emails
EXTRACTORS["classify_email"] = extract_classification
EXTRACTORS["get_today_events"] = extract_calendar
EXTRACTORS["get_upcoming_events"] = extract_calendar
EXTRACTORS["generate_meeting_brief"] = extract_calendar
EXTRACTORS["search_memory"] = extract_memory_results
EXTRACTORS["store_observation"] = extract_observation


def get_extractor(tool_name: str) -> ExtractorFn | None:
    """Get the extractor function for a given tool name."""
    return EXTRACTORS.get(tool_name)
