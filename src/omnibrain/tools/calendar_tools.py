"""
OmniBrain — Calendar Tools

Omnigent-compatible tool handlers for Google Calendar operations.
These are the functions that the AI agent calls to interact with Calendar.

Tools defined here:
    get_today_events     — Fetch today's calendar events (pre-approved, read-only)
    get_upcoming_events  — Fetch upcoming events for N days (pre-approved, read-only)
    generate_meeting_brief — Generate a briefing for an upcoming meeting (pre-approved)

Architecture:
    Agent calls tool → tool handler → CalendarClient → Calendar API → CalendarEvent
                                   → stores in db.events
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from omnibrain.integrations.calendar import CalendarAuthError, CalendarClient
from omnibrain.models import CalendarEvent, EventSource

logger = logging.getLogger("omnibrain.tools.calendar")


# ═══════════════════════════════════════════════════════════════════════════
# Tool: get_today_events
# ═══════════════════════════════════════════════════════════════════════════

GET_TODAY_EVENTS_SCHEMA = {
    "name": "get_today_events",
    "description": "Fetch all calendar events for today. Returns title, time, duration, attendees, and location.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


def get_today_events(data_dir: Path) -> dict[str, Any]:
    """Fetch today's calendar events.

    Returns:
        Dict with 'events' list and metadata, suitable for agent consumption.
    """
    client = CalendarClient(data_dir)

    if not client.authenticate():
        return {
            "error": "Calendar not authenticated. Run 'omnibrain setup-google' first.",
            "events": [],
            "count": 0,
        }

    try:
        events = client.get_today_events()
        event_dicts = [_event_to_agent_view(e) for e in events]

        return {
            "events": event_dicts,
            "count": len(event_dicts),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": _make_day_summary(events),
        }

    except CalendarAuthError as e:
        return {
            "error": f"Authentication error: {e}. Run 'omnibrain setup-google'.",
            "events": [],
            "count": 0,
        }
    except Exception as e:
        logger.error(f"get_today_events failed: {e}")
        return {
            "error": f"Failed to fetch calendar events: {e}",
            "events": [],
            "count": 0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Tool: get_upcoming_events
# ═══════════════════════════════════════════════════════════════════════════

GET_UPCOMING_EVENTS_SCHEMA = {
    "name": "get_upcoming_events",
    "description": "Fetch upcoming calendar events for the next N days. Returns title, time, duration, attendees, and location.",
    "parameters": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days to look ahead (1-30)",
                "default": 7,
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum events to return (1-50)",
                "default": 20,
            },
        },
    },
}


def get_upcoming_events(
    data_dir: Path,
    days: int = 7,
    max_results: int = 20,
) -> dict[str, Any]:
    """Fetch upcoming calendar events for next N days.

    Returns:
        Dict with 'events' list and metadata.
    """
    client = CalendarClient(data_dir)

    if not client.authenticate():
        return {
            "error": "Calendar not authenticated. Run 'omnibrain setup-google' first.",
            "events": [],
            "count": 0,
        }

    try:
        events = client.get_upcoming_events(days=days, max_results=max_results)
        event_dicts = [_event_to_agent_view(e) for e in events]

        return {
            "events": event_dicts,
            "count": len(event_dicts),
            "days_ahead": days,
            "summary": _make_week_summary(events, days),
        }

    except CalendarAuthError as e:
        return {
            "error": f"Authentication error: {e}",
            "events": [],
            "count": 0,
        }
    except Exception as e:
        logger.error(f"get_upcoming_events failed: {e}")
        return {
            "error": f"Failed to fetch upcoming events: {e}",
            "events": [],
            "count": 0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Tool: generate_meeting_brief
# ═══════════════════════════════════════════════════════════════════════════

GENERATE_MEETING_BRIEF_SCHEMA = {
    "name": "generate_meeting_brief",
    "description": "Generate a pre-meeting briefing with attendee context, recent interactions, and agenda preparation.",
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The calendar event ID to brief on",
            },
        },
        "required": ["event_id"],
    },
}


def generate_meeting_brief(
    data_dir: Path,
    event_id: str,
    db: Any = None,
) -> dict[str, Any]:
    """Generate a meeting brief for a specific event.

    Combines event info with contact history from DB.

    Args:
        data_dir: Path to data directory.
        event_id: Calendar event ID.
        db: Optional OmniBrainDB instance (if None, creates one).

    Returns:
        Dict with meeting brief details.
    """
    client = CalendarClient(data_dir)

    if not client.authenticate():
        return {"error": "Calendar not authenticated."}

    event = client.get_event(event_id)
    if not event:
        return {"error": f"Event {event_id} not found."}

    # Build attendee context from DB
    attendee_context = []
    if db:
        for email in event.attendees:
            contact = db.get_contact(email)
            if contact:
                attendee_context.append({
                    "email": email,
                    "name": contact.get("name", ""),
                    "relationship": contact.get("relationship", "unknown"),
                    "organization": contact.get("organization", ""),
                    "interaction_count": contact.get("interaction_count", 0),
                    "last_interaction": contact.get("last_interaction", ""),
                })
            else:
                attendee_context.append({
                    "email": email,
                    "name": "",
                    "relationship": "unknown",
                    "known": False,
                })

    return {
        "event": _event_to_agent_view(event),
        "attendee_context": attendee_context,
        "attendee_count": len(event.attendees),
        "duration_minutes": event.duration_minutes,
        "has_description": bool(event.description),
        "is_recurring": event.is_recurring,
        "preparation_notes": _generate_prep_notes(event, attendee_context),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Storage
# ═══════════════════════════════════════════════════════════════════════════


def store_events_in_db(
    events: list[CalendarEvent],
    db: Any,
) -> int:
    """Store fetched calendar events as events in the DB.

    Returns:
        Number of events stored.
    """
    events_stored = 0

    for event in events:
        try:
            metadata = {
                "calendar_id": event.id,
                "attendees": event.attendees,
                "location": event.location,
                "is_recurring": event.is_recurring,
                "duration_minutes": event.duration_minutes,
                "start_time": event.start_time.isoformat(),
                "end_time": event.end_time.isoformat(),
            }

            db.insert_event(
                source=EventSource.CALENDAR.value,
                event_type="calendar_event",
                title=event.title,
                content=event.description[:2000] if event.description else "",
                metadata=metadata,
                priority=0,
            )
            events_stored += 1
        except Exception as e:
            logger.warning(f"Failed to store calendar event {event.id}: {e}")

    if events_stored:
        logger.info(f"Stored {events_stored} calendar events in DB")
    return events_stored


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _event_to_agent_view(event: CalendarEvent) -> dict[str, Any]:
    """Convert CalendarEvent to a dict optimized for LLM agent consumption."""
    return {
        "id": event.id,
        "title": event.title,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "duration_minutes": event.duration_minutes,
        "attendees": event.attendees,
        "attendees_summary": event.attendees_summary,
        "location": event.location,
        "description": event.description[:300] if event.description else "",
        "is_recurring": event.is_recurring,
    }


def _make_day_summary(events: list[CalendarEvent]) -> str:
    """Generate a human-readable summary of today's events."""
    if not events:
        return "No events today."

    total_minutes = sum(e.duration_minutes for e in events)
    hours = total_minutes // 60
    minutes = total_minutes % 60

    lines = [f"{len(events)} events today ({hours}h {minutes}m total):"]
    for e in events:
        time_str = e.start_time.strftime("%H:%M")
        lines.append(f"  • {time_str} — {e.title} ({e.duration_minutes}min, {e.attendees_summary})")

    return "\n".join(lines)


def _make_week_summary(events: list[CalendarEvent], days: int) -> str:
    """Generate a summary of upcoming events."""
    if not events:
        return f"No events in the next {days} days."

    # Group by date
    by_date: dict[str, list[CalendarEvent]] = {}
    for e in events:
        date_key = e.start_time.strftime("%Y-%m-%d (%A)")
        by_date.setdefault(date_key, []).append(e)

    lines = [f"{len(events)} events in next {days} days:"]
    for date, day_events in by_date.items():
        lines.append(f"\n  {date}:")
        for e in day_events:
            time_str = e.start_time.strftime("%H:%M")
            lines.append(f"    • {time_str} — {e.title} ({e.duration_minutes}min)")

    return "\n".join(lines)


def _generate_prep_notes(
    event: CalendarEvent,
    attendee_context: list[dict[str, Any]],
) -> str:
    """Generate preparation notes for a meeting."""
    notes = []

    # Meeting basics
    notes.append(f"Meeting: {event.title}")
    notes.append(f"Duration: {event.duration_minutes} minutes")
    if event.location:
        notes.append(f"Location: {event.location}")

    # Attendee insights
    known = [a for a in attendee_context if a.get("interaction_count", 0) > 0]
    unknown = [a for a in attendee_context if a.get("interaction_count", 0) == 0]

    if known:
        notes.append(f"\nKnown attendees ({len(known)}):")
        for a in known:
            name = a.get("name") or a["email"]
            rel = a.get("relationship", "unknown")
            count = a.get("interaction_count", 0)
            notes.append(f"  • {name} — {rel}, {count} interactions")

    if unknown:
        notes.append(f"\nNew/unknown attendees ({len(unknown)}):")
        for a in unknown:
            notes.append(f"  • {a['email']}")

    return "\n".join(notes)


# ═══════════════════════════════════════════════════════════════════════════
# All tool schemas (for registry)
# ═══════════════════════════════════════════════════════════════════════════

CALENDAR_TOOL_SCHEMAS = [
    GET_TODAY_EVENTS_SCHEMA,
    GET_UPCOMING_EVENTS_SCHEMA,
    GENERATE_MEETING_BRIEF_SCHEMA,
]
