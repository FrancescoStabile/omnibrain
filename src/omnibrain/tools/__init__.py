"""OmniBrain tools — Omnigent tool handlers for all OmniBrain capabilities.

Available tools:
    email_tools    — fetch_emails, classify_email, search_emails, draft_email
    calendar_tools — get_today_events, get_upcoming_events, generate_meeting_brief
    memory_tools   — search_memory, store_observation
    action_tools   — (Phase 1 Day 13-14)
"""

from omnibrain.tools.email_tools import (
    EMAIL_TOOL_SCHEMAS,
    FETCH_EMAILS_SCHEMA,
    SEARCH_EMAILS_SCHEMA,
    CLASSIFY_EMAIL_SCHEMA,
    fetch_emails,
    search_emails,
    classify_email,
    store_emails_in_db,
)

from omnibrain.tools.calendar_tools import (
    CALENDAR_TOOL_SCHEMAS,
    GET_TODAY_EVENTS_SCHEMA,
    GET_UPCOMING_EVENTS_SCHEMA,
    GENERATE_MEETING_BRIEF_SCHEMA,
    get_today_events,
    get_upcoming_events,
    generate_meeting_brief,
    store_events_in_db,
)

from omnibrain.tools.memory_tools import (
    MEMORY_TOOL_SCHEMAS,
    SEARCH_MEMORY_SCHEMA,
    STORE_OBSERVATION_SCHEMA,
    search_memory,
    store_observation,
    ingest_emails_to_memory,
    ingest_events_to_memory,
)

__all__ = [
    # Email tools
    "EMAIL_TOOL_SCHEMAS",
    "FETCH_EMAILS_SCHEMA",
    "SEARCH_EMAILS_SCHEMA",
    "CLASSIFY_EMAIL_SCHEMA",
    "fetch_emails",
    "search_emails",
    "classify_email",
    "store_emails_in_db",
    # Calendar tools
    "CALENDAR_TOOL_SCHEMAS",
    "GET_TODAY_EVENTS_SCHEMA",
    "GET_UPCOMING_EVENTS_SCHEMA",
    "GENERATE_MEETING_BRIEF_SCHEMA",
    "get_today_events",
    "get_upcoming_events",
    "generate_meeting_brief",
    "store_events_in_db",
    # Memory tools
    "MEMORY_TOOL_SCHEMAS",
    "SEARCH_MEMORY_SCHEMA",
    "STORE_OBSERVATION_SCHEMA",
    "search_memory",
    "store_observation",
    "ingest_emails_to_memory",
    "ingest_events_to_memory",
]
