"""
OmniBrain — Chat Tool Definitions

Defines the tools that the chat LLM can invoke to perform real actions
on the user's data (events, contacts, proposals, etc.).

Each tool has:
- An OpenAI-format JSON schema (for the LLM)
- An async executor function (called when the LLM invokes the tool)

Tool schemas use OpenAI function calling format:
  {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("omnibrain.chat_tools")


# ═══════════════════════════════════════════════════════════════════════════
# Tool Schemas — OpenAI function-calling format
# ═══════════════════════════════════════════════════════════════════════════

CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": (
                "Search for events/appointments/commitments in the user's calendar. "
                "Use this to find events before modifying or deleting them. "
                "Returns a list of matching events with their IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search query (e.g. 'dentist', 'meeting with Marco')",
                    },
                    "since": {
                        "type": "string",
                        "description": "ISO date string — only return events after this date (e.g. '2025-01-20')",
                    },
                    "until": {
                        "type": "string",
                        "description": "ISO date string — only return events before this date (e.g. '2025-01-27')",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": (
                "List events in a date range. Use this to show the user their upcoming "
                "schedule or commitments for a specific period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "since": {
                        "type": "string",
                        "description": "ISO date string — start of range (e.g. '2025-01-20')",
                    },
                    "until": {
                        "type": "string",
                        "description": "ISO date string — end of range (e.g. '2025-01-27')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of events to return (default 20)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": (
                "Delete an event/appointment/commitment by its ID. "
                "IMPORTANT: Always search for the event first to confirm the correct ID "
                "before deleting. Tell the user which event you are deleting."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "integer",
                        "description": "The ID of the event to delete",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": (
                "Create a new event/appointment/commitment in the user's calendar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title/name of the event",
                    },
                    "timestamp": {
                        "type": "string",
                        "description": "When the event occurs — ISO datetime (e.g. '2025-01-25 14:00:00')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Additional details or notes about the event",
                    },
                    "event_type": {
                        "type": "string",
                        "description": "Type of event (e.g. 'appointment', 'meeting', 'reminder', 'task')",
                    },
                },
                "required": ["title", "timestamp"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_event",
            "description": (
                "Update an existing event/appointment. Only the fields you provide will be changed. "
                "IMPORTANT: Search for the event first to get its ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "integer",
                        "description": "The ID of the event to update",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title (omit to keep current)",
                    },
                    "timestamp": {
                        "type": "string",
                        "description": "New date/time in ISO format (omit to keep current)",
                    },
                    "content": {
                        "type": "string",
                        "description": "New content/notes (omit to keep current)",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_contacts",
            "description": "List the user's known contacts, ordered by interaction frequency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of contacts to return (default 20)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_proposals",
            "description": "List pending proposals/suggestions that the user can approve or reject.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_proposal",
            "description": "Approve a pending proposal by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "integer",
                        "description": "The ID of the proposal to approve",
                    },
                },
                "required": ["proposal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_proposal",
            "description": "Reject a pending proposal by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "integer",
                        "description": "The ID of the proposal to reject",
                    },
                },
                "required": ["proposal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_preference",
            "description": (
                "Save a user preference or personal fact that OmniBrain should remember. "
                "Examples: preferred wake-up time, dietary restrictions, work schedule, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Preference key (e.g. 'wake_up_time', 'favorite_food')",
                    },
                    "value": {
                        "type": "string",
                        "description": "The preference value",
                    },
                },
                "required": ["key", "value"],
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# Tool Executors
# ═══════════════════════════════════════════════════════════════════════════


async def execute_tool(
    db: Any,
    tool_name: str,
    arguments: dict[str, Any],
    calendar_client: Any | None = None,
) -> str:
    """Execute a chat tool and return a JSON-serializable result string.

    Args:
        db: OmniBrainDB instance
        tool_name: Name of the tool to execute
        arguments: Tool arguments (already parsed from JSON)
        calendar_client: Optional CalendarClient for Google Calendar sync

    Returns:
        A string describing the result (will be sent back to the LLM as tool result)
    """
    try:
        handler = _TOOL_HANDLERS.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        result = await handler(db, arguments, calendar_client)
        return result
    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name}({arguments}): {e}", exc_info=True)
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})


# ── Individual handlers ──


async def _search_events(db: Any, args: dict, cal: Any = None) -> str:
    query = args.get("query", "")
    since_str = args.get("since")
    until_str = args.get("until")

    if query:
        # Use FTS search
        events = db.search_events(query, limit=30)
    else:
        # Use date-range filter
        since = datetime.fromisoformat(since_str) if since_str else None
        until = datetime.fromisoformat(until_str) if until_str else None
        events = db.get_events(since=since, until=until, limit=30)

    # Apply date filters to FTS results too if provided
    if query and (since_str or until_str):
        filtered = []
        for e in events:
            ts = e.get("timestamp", "")
            if since_str and ts < since_str:
                continue
            if until_str and ts > until_str:
                continue
            filtered.append(e)
        events = filtered

    if not events:
        return json.dumps({"events": [], "message": "No events found matching the criteria."})

    simplified = []
    for e in events:
        simplified.append({
            "id": e["id"],
            "title": e["title"],
            "timestamp": e.get("timestamp", ""),
            "type": e.get("event_type", ""),
            "content": (e.get("content", "") or "")[:200],
        })
    return json.dumps({"events": simplified, "count": len(simplified)})


async def _list_events(db: Any, args: dict, cal: Any = None) -> str:
    since_str = args.get("since")
    until_str = args.get("until")
    limit = args.get("limit", 20)

    since = datetime.fromisoformat(since_str) if since_str else None
    until = datetime.fromisoformat(until_str) if until_str else None
    events = db.get_events(since=since, until=until, limit=limit)

    if not events:
        return json.dumps({"events": [], "message": "No events in the specified range."})

    simplified = []
    for e in events:
        simplified.append({
            "id": e["id"],
            "title": e["title"],
            "timestamp": e.get("timestamp", ""),
            "type": e.get("event_type", ""),
            "content": (e.get("content", "") or "")[:200],
        })
    return json.dumps({"events": simplified, "count": len(simplified)})


async def _delete_event(db: Any, args: dict, cal: Any = None) -> str:
    event_id = args.get("event_id")
    if event_id is None:
        return json.dumps({"error": "event_id is required"})

    # Get event details first for confirmation message
    event = db.get_event_by_id(int(event_id))
    if not event:
        return json.dumps({"error": f"Event with ID {event_id} not found."})

    title = event.get("title", "Unknown")
    timestamp = event.get("timestamp", "")
    external_id = event.get("external_id")
    source = event.get("source", "")

    # If this is a Google Calendar event, also delete from Google
    google_deleted = False
    if cal and external_id and source == "calendar":
        try:
            google_deleted = cal.delete_event(external_id)
        except Exception as e:
            logger.warning(f"Google Calendar delete failed for {external_id}: {e}")

    deleted = db.delete_event(int(event_id))
    if deleted:
        msg = f"Event '{title}' (scheduled for {timestamp}) has been deleted."
        if google_deleted:
            msg += " Also removed from Google Calendar."
        return json.dumps({
            "success": True,
            "message": msg,
            "deleted_event": {"id": event_id, "title": title, "timestamp": timestamp},
        })
    else:
        return json.dumps({"error": f"Failed to delete event {event_id}."})


async def _create_event(db: Any, args: dict, cal: Any = None) -> str:
    title = args.get("title", "")
    timestamp = args.get("timestamp", "")
    content = args.get("content", "")
    event_type = args.get("event_type", "appointment")

    if not title:
        return json.dumps({"error": "title is required"})
    if not timestamp:
        return json.dumps({"error": "timestamp is required"})

    # Try to create on Google Calendar first
    google_event = None
    external_id = None
    source = "chat"
    if cal:
        try:
            start_dt = datetime.fromisoformat(timestamp)
            google_event = cal.create_event(
                title=title,
                start_time=start_dt,
                description=content,
            )
            if google_event:
                external_id = google_event.id
                source = "calendar"  # Mark as calendar source so collector won't dupe
                logger.info(f"Created Google Calendar event: {google_event.id}")
        except Exception as e:
            logger.warning(f"Google Calendar create failed, saving locally: {e}")

    event_id = db.insert_event(
        source=source,
        event_type=event_type,
        title=title,
        content=content,
        timestamp=timestamp,
        external_id=external_id,
    )
    msg = f"Event '{title}' created for {timestamp}."
    if google_event:
        msg += " Synced to Google Calendar."
    return json.dumps({
        "success": True,
        "event_id": event_id,
        "message": msg,
    })


async def _update_event(db: Any, args: dict, cal: Any = None) -> str:
    event_id = args.get("event_id")
    if event_id is None:
        return json.dumps({"error": "event_id is required"})

    # Check event exists
    event = db.get_event_by_id(int(event_id))
    if not event:
        return json.dumps({"error": f"Event with ID {event_id} not found."})

    external_id = event.get("external_id")
    source = event.get("source", "")

    # If Google Calendar event, update there too
    google_updated = False
    if cal and external_id and source == "calendar":
        try:
            new_start = None
            if args.get("timestamp"):
                new_start = datetime.fromisoformat(args["timestamp"])
            gcal_event = cal.update_event(
                event_id=external_id,
                title=args.get("title"),
                start_time=new_start,
                description=args.get("content"),
            )
            google_updated = gcal_event is not None
        except Exception as e:
            logger.warning(f"Google Calendar update failed for {external_id}: {e}")

    updated = db.update_event(
        event_id=int(event_id),
        title=args.get("title"),
        content=args.get("content"),
        timestamp=args.get("timestamp"),
    )
    if updated:
        msg = f"Event {event_id} updated."
        if google_updated:
            msg += " Synced to Google Calendar."
        return json.dumps({
            "success": True,
            "message": msg,
        })
    else:
        return json.dumps({"error": "No fields to update or event not found."})


async def _list_contacts(db: Any, args: dict, cal: Any = None) -> str:
    limit = args.get("limit", 20)
    contacts = db.get_contacts(limit=limit)
    if not contacts:
        return json.dumps({"contacts": [], "message": "No contacts found."})

    simplified = []
    for c in contacts:
        d = c.to_dict() if hasattr(c, "to_dict") else c
        simplified.append({
            "name": d.get("name", ""),
            "email": d.get("email", ""),
            "relationship": d.get("relationship", ""),
            "organization": d.get("organization", ""),
            "interaction_count": d.get("interaction_count", 0),
        })
    return json.dumps({"contacts": simplified, "count": len(simplified)})


async def _list_proposals(db: Any, args: dict, cal: Any = None) -> str:
    proposals = db.get_pending_proposals()
    if not proposals:
        return json.dumps({"proposals": [], "message": "No pending proposals."})

    simplified = []
    for p in proposals:
        simplified.append({
            "id": p["id"],
            "type": p.get("type", ""),
            "title": p.get("title", ""),
            "description": (p.get("description", "") or "")[:200],
            "priority": p.get("priority", 0),
        })
    return json.dumps({"proposals": simplified, "count": len(simplified)})


async def _approve_proposal(db: Any, args: dict, cal: Any = None) -> str:
    proposal_id = args.get("proposal_id")
    if proposal_id is None:
        return json.dumps({"error": "proposal_id is required"})

    updated = db.update_proposal_status(int(proposal_id), "approved")
    if updated:
        return json.dumps({"success": True, "message": f"Proposal {proposal_id} approved."})
    else:
        return json.dumps({"error": f"Proposal {proposal_id} not found."})


async def _reject_proposal(db: Any, args: dict, cal: Any = None) -> str:
    proposal_id = args.get("proposal_id")
    if proposal_id is None:
        return json.dumps({"error": "proposal_id is required"})

    updated = db.update_proposal_status(int(proposal_id), "rejected")
    if updated:
        return json.dumps({"success": True, "message": f"Proposal {proposal_id} rejected."})
    else:
        return json.dumps({"error": f"Proposal {proposal_id} not found."})


async def _set_preference(db: Any, args: dict, cal: Any = None) -> str:
    key = args.get("key", "")
    value = args.get("value", "")
    if not key:
        return json.dumps({"error": "key is required"})

    db.set_preference(key, value, confidence=0.9, learned_from="chat_tool")
    return json.dumps({"success": True, "message": f"Preference '{key}' saved."})


# ── Handler Registry ──

_TOOL_HANDLERS = {
    "search_events": _search_events,
    "list_events": _list_events,
    "delete_event": _delete_event,
    "create_event": _create_event,
    "update_event": _update_event,
    "list_contacts": _list_contacts,
    "list_proposals": _list_proposals,
    "approve_proposal": _approve_proposal,
    "reject_proposal": _reject_proposal,
    "set_preference": _set_preference,
}
