"""
OmniBrain — Email Tools

Omnigent-compatible tool handlers for email operations.
These are the functions that the AI agent calls to interact with Gmail.

Tools defined here:
    fetch_emails       — Fetch recent emails (pre-approved, read-only)
    classify_email     — LLM-based email triage (pre-approved)
    draft_email        — Generate email draft (pre-approved, just creates proposal)
    search_emails      — Search Gmail with Gmail query syntax (pre-approved)

Architecture:
    Agent calls tool → tool handler → GmailClient → Gmail API → EmailMessage
                                   → stores in db.events + db.contacts
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from omnibrain.integrations.gmail import GmailAuthError, GmailClient
from omnibrain.models import ContactInfo, EmailMessage, EventSource

logger = logging.getLogger("omnibrain.tools.email")


# ═══════════════════════════════════════════════════════════════════════════
# Tool: fetch_emails
# ═══════════════════════════════════════════════════════════════════════════

FETCH_EMAILS_SCHEMA = {
    "name": "fetch_emails",
    "description": "Fetch recent emails from inbox. Returns sender, subject, date, and body preview.",
    "parameters": {
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "description": "Max emails to fetch (1-100)",
                "default": 20,
            },
            "query": {
                "type": "string",
                "description": "Gmail search query (supports full Gmail syntax: from:, subject:, is:unread, etc.)",
                "default": "",
            },
            "since_hours": {
                "type": "integer",
                "description": "Only fetch emails from the last N hours",
                "default": 24,
            },
        },
    },
}


def fetch_emails(
    data_dir: Path,
    max_results: int = 20,
    query: str = "",
    since_hours: int = 24,
) -> dict[str, Any]:
    """Fetch recent emails from Gmail.

    Returns:
        Dict with 'emails' list and metadata, suitable for agent consumption.
    """
    client = GmailClient(data_dir)

    if not client.authenticate():
        return {
            "error": "Gmail not authenticated. Run 'omnibrain setup-google' first.",
            "emails": [],
            "count": 0,
        }

    try:
        emails = client.fetch_recent(
            max_results=max_results,
            query=query,
            since_hours=since_hours,
        )

        # Convert to serializable format for agent
        email_dicts = [_email_to_agent_view(e) for e in emails]

        return {
            "emails": email_dicts,
            "count": len(email_dicts),
            "query": query or "(all recent)",
            "since_hours": since_hours,
            "user_email": client.user_email,
        }

    except GmailAuthError as e:
        return {
            "error": f"Authentication error: {e}. Run 'omnibrain setup-google'.",
            "emails": [],
            "count": 0,
        }
    except Exception as e:
        logger.error(f"fetch_emails failed: {e}")
        return {
            "error": f"Failed to fetch emails: {e}",
            "emails": [],
            "count": 0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Tool: search_emails
# ═══════════════════════════════════════════════════════════════════════════

SEARCH_EMAILS_SCHEMA = {
    "name": "search_emails",
    "description": "Search emails using Gmail search syntax. Examples: 'from:boss@company.com', 'subject:invoice', 'is:unread label:important'",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Gmail search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Max results to return",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}


def search_emails(
    data_dir: Path,
    query: str,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search Gmail with full search syntax."""
    client = GmailClient(data_dir)

    if not client.authenticate():
        return {"error": "Gmail not authenticated.", "emails": [], "count": 0}

    try:
        emails = client.search(query=query, max_results=max_results)
        email_dicts = [_email_to_agent_view(e) for e in emails]
        return {
            "emails": email_dicts,
            "count": len(email_dicts),
            "query": query,
        }
    except GmailAuthError as e:
        return {"error": f"Auth error: {e}", "emails": [], "count": 0}
    except Exception as e:
        logger.error(f"search_emails failed: {e}")
        return {"error": str(e), "emails": [], "count": 0}


# ═══════════════════════════════════════════════════════════════════════════
# Tool: classify_email
# ═══════════════════════════════════════════════════════════════════════════

CLASSIFY_EMAIL_SCHEMA = {
    "name": "classify_email",
    "description": "Classify an email's urgency and required action using LLM analysis.",
    "parameters": {
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "The email message ID"},
            "sender": {"type": "string", "description": "Sender email address"},
            "subject": {"type": "string", "description": "Email subject line"},
            "body_preview": {"type": "string", "description": "First ~200 chars of body"},
        },
        "required": ["email_id", "subject"],
    },
}


def classify_email(
    data_dir: Path,
    email_id: str,
    subject: str,
    sender: str = "",
    body_preview: str = "",
) -> dict[str, Any]:
    """Classify email urgency via keyword heuristics.

    Returns structured classification with urgency, category, action, and
    whether a draft reply is recommended.
    """
    urgency = "medium"
    category = "fyi"
    action = "archive"
    draft_needed = False

    subject_lower = subject.lower()
    body_lower = body_preview.lower()
    combined = f"{subject_lower} {body_lower}"

    # Heuristic urgency detection
    if any(w in combined for w in ["urgent", "asap", "emergency", "critical", "deadline today"]):
        urgency = "high"
        category = "action_required"
        action = "respond"
        draft_needed = True
    elif any(w in combined for w in ["action required", "please respond", "waiting for", "follow up"]):
        urgency = "medium"
        category = "action_required"
        action = "respond"
        draft_needed = True
    elif any(w in combined for w in ["unsubscribe", "newsletter", "digest", "weekly update"]):
        urgency = "low"
        category = "newsletter"
        action = "archive"
    elif any(w in combined for w in ["no-reply", "noreply", "notification", "automated"]):
        urgency = "low"
        category = "notification"
        action = "archive"
    elif any(w in combined for w in ["invoice", "payment", "receipt", "order confirmation"]):
        urgency = "medium"
        category = "transactional"
        action = "archive"

    return {
        "email_id": email_id,
        "urgency": urgency,
        "category": category,
        "action": action,
        "reasoning": "Heuristic keyword-based classification",
        "draft_needed": draft_needed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _email_to_agent_view(email: EmailMessage) -> dict[str, Any]:
    """Convert EmailMessage to a dict optimized for LLM agent consumption.

    Includes sender info, subject, date, body preview, and metadata.
    Body is truncated to 500 chars to save context window.
    """
    return {
        "id": email.id,
        "thread_id": email.thread_id,
        "sender": email.sender,
        "sender_email": email.sender_email,
        "sender_name": email.sender_name,
        "recipients": email.recipients,
        "subject": email.subject,
        "body_preview": email.body[:500] if email.body else "",
        "date": email.date.isoformat(),
        "is_read": email.is_read,
        "has_attachments": email.has_attachments,
        "labels": email.labels,
    }


def store_emails_in_db(
    emails: list[EmailMessage],
    db: Any,  # OmniBrainDB — Any to avoid circular import
) -> tuple[int, int]:
    """Store fetched emails as events and update contacts in DB.

    Returns:
        Tuple of (events_stored, contacts_updated).

    This is the "extractor" from manifesto Section 9 — takes raw emails
    and stores structured data in events table + updates contacts table.
    """
    events_stored = 0
    contacts_updated = 0

    for email in emails:
        # Store as event
        try:
            metadata = {
                "gmail_id": email.id,
                "thread_id": email.thread_id,
                "sender": email.sender,
                "sender_email": email.sender_email,
                "recipients": email.recipients,
                "is_read": email.is_read,
                "has_attachments": email.has_attachments,
                "labels": email.labels,
            }

            db.insert_event(
                source=EventSource.GMAIL.value,
                event_type="email",
                title=f"Email from {email.sender_name or email.sender_email}: {email.subject}",
                content=email.body[:2000] if email.body else "",  # Cap body at 2KB
                metadata=metadata,
                priority=0,
                timestamp=email.date.isoformat() if email.date else None,
                external_id=email.id,
            )
            events_stored += 1
        except Exception as e:
            logger.warning(f"Failed to store email event {email.id}: {e}")

        # Upsert contact from sender
        try:
            contact = ContactInfo(
                email=email.sender_email,
                name=email.sender_name,
                last_interaction=email.date,
            )
            db.upsert_contact(contact)
            contacts_updated += 1
        except Exception as e:
            logger.warning(f"Failed to upsert contact {email.sender_email}: {e}")

    logger.info(f"Stored {events_stored} email events, updated {contacts_updated} contacts")
    return events_stored, contacts_updated


# ═══════════════════════════════════════════════════════════════════════════
# All tool schemas (for registry)
# ═══════════════════════════════════════════════════════════════════════════

EMAIL_TOOL_SCHEMAS = [
    FETCH_EMAILS_SCHEMA,
    SEARCH_EMAILS_SCHEMA,
    CLASSIFY_EMAIL_SCHEMA,
]
