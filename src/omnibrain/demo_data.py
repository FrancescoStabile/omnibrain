"""
OmniBrain — Demo Mode

Populates the database with realistic sample data so first-time users
(or anyone without Google connected) see a fully working product instead
of empty screens.

Usage:
    from omnibrain.demo_data import DemoDataManager

    mgr = DemoDataManager(db, memory)
    if not mgr.is_active():
        mgr.activate()   # install demo data
    # ...later, when real data arrives...
    mgr.deactivate()     # wipe demo data

All demo records are tagged with source="demo" so they can be identified
and removed cleanly when real data is available.

The UI badge: any record with source="demo" or source_type="demo" gets a
"📋 Demo" badge rendered by the frontend.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("omnibrain.demo")

# ─────────────────────────────────────────────────────────────────────────────
# Sample data
# ─────────────────────────────────────────────────────────────────────────────

_NOW = datetime.now()
_d = lambda days: (_NOW - timedelta(days=days)).isoformat()  # noqa: E731


DEMO_CONTACTS: list[dict[str, Any]] = [
    {
        "email": "marco.rossi@acmecorp.com",
        "name": "Marco Rossi",
        "relationship": "colleague",
        "organization": "Acme Corp",
        "interaction_count": 47,
    },
    {
        "email": "giulia.ferrari@startup.io",
        "name": "Giulia Ferrari",
        "relationship": "client",
        "organization": "Startup.io",
        "interaction_count": 23,
    },
    {
        "email": "luca.bianchi@investor.vc",
        "name": "Luca Bianchi",
        "relationship": "investor",
        "organization": "Bianchi Ventures",
        "interaction_count": 8,
    },
    {
        "email": "sofia.ricci@partner.com",
        "name": "Sofia Ricci",
        "relationship": "partner",
        "organization": "Design Studio",
        "interaction_count": 31,
    },
    {
        "email": "andrea.conti@client.com",
        "name": "Andrea Conti",
        "relationship": "client",
        "organization": "Global Corp",
        "interaction_count": 15,
    },
    {
        "email": "elena.mancini@team.com",
        "name": "Elena Mancini",
        "relationship": "colleague",
        "organization": "Your Company",
        "interaction_count": 62,
    },
    {
        "email": "roberto.palma@tech.com",
        "name": "Roberto Palma",
        "relationship": "colleague",
        "organization": "Your Company",
        "interaction_count": 19,
    },
    {
        "email": "silvia.romano@agency.it",
        "name": "Silvia Romano",
        "relationship": "vendor",
        "organization": "Creative Agency",
        "interaction_count": 11,
    },
    {
        "email": "matteo.gallo@lead.com",
        "name": "Matteo Gallo",
        "relationship": "prospect",
        "organization": "Future Client Ltd",
        "interaction_count": 5,
    },
    {
        "email": "valentina.russo@media.com",
        "name": "Valentina Russo",
        "relationship": "press",
        "organization": "Tech Media",
        "interaction_count": 3,
    },
]

DEMO_EMAILS: list[dict[str, Any]] = [
    {
        "source": "demo",
        "title": "Re: Q1 proposal — follow-up needed",
        "priority": 3,
        "metadata": json.dumps({
            "from": "marco.rossi@acmecorp.com",
            "to": ["you@yourcompany.com"],
            "subject": "Re: Q1 proposal",
            "snippet": "Hi, following up on the Q1 proposal we discussed. Can we schedule a call this week to finalize the numbers?",
            "thread_id": "demo_thread_1",
            "is_demo": True,
        }),
        "timestamp": _d(0),
    },
    {
        "source": "demo",
        "title": "Invoice overdue — Action Required",
        "priority": 4,
        "metadata": json.dumps({
            "from": "billing@supplier.com",
            "to": ["you@yourcompany.com"],
            "subject": "Invoice #2024-089 overdue",
            "snippet": "Your invoice #2024-089 for €2,400 is now 7 days overdue. Please process payment to avoid service interruption.",
            "is_demo": True,
        }),
        "timestamp": _d(1),
    },
    {
        "source": "demo",
        "title": "Product feedback from Giulia",
        "priority": 2,
        "metadata": json.dumps({
            "from": "giulia.ferrari@startup.io",
            "to": ["you@yourcompany.com"],
            "subject": "Feedback on latest release",
            "snippet": "Loving the new dashboard! One thing — the export function crashes on large datasets. Our team uses it daily for the weekly report.",
            "is_demo": True,
        }),
        "timestamp": _d(1),
    },
    {
        "source": "demo",
        "title": "Meeting recap — Product roadmap",
        "priority": 1,
        "metadata": json.dumps({
            "from": "elena.mancini@team.com",
            "to": ["you@yourcompany.com", "roberto.palma@tech.com"],
            "subject": "Meeting recap: Product Roadmap Q1",
            "snippet": "Summary of today's meeting: 1. MVP scope confirmed. 2. Design sprint starts Monday. 3. Beta target: March 15.",
            "is_demo": True,
        }),
        "timestamp": _d(2),
    },
    {
        "source": "demo",
        "title": "Investment opportunity — interested",
        "priority": 3,
        "metadata": json.dumps({
            "from": "luca.bianchi@investor.vc",
            "to": ["you@yourcompany.com"],
            "subject": "Following up on our conversation",
            "snippet": "After reviewing the deck, we're interested in proceeding. Our typical check size is €300K-500K. Can you send the cap table?",
            "is_demo": True,
        }),
        "timestamp": _d(3),
    },
]

DEMO_CALENDAR: list[dict[str, Any]] = [
    {
        "source": "demo",
        "title": "Standup — Engineering Team",
        "priority": 1,
        "metadata": json.dumps({
            "start": (_NOW + timedelta(hours=2)).isoformat(),
            "end": (_NOW + timedelta(hours=2, minutes=30)).isoformat(),
            "attendees": [
                {"email": "elena.mancini@team.com", "name": "Elena Mancini"},
                {"email": "roberto.palma@tech.com", "name": "Roberto Palma"},
            ],
            "location": "Google Meet",
            "is_demo": True,
        }),
        "timestamp": (_NOW + timedelta(hours=2)).isoformat(),
    },
    {
        "source": "demo",
        "title": "Client review — Q1 roadmap",
        "priority": 2,
        "metadata": json.dumps({
            "start": (_NOW + timedelta(hours=5)).isoformat(),
            "end": (_NOW + timedelta(hours=6)).isoformat(),
            "attendees": [
                {"email": "marco.rossi@acmecorp.com", "name": "Marco Rossi"},
                {"email": "giulia.ferrari@startup.io", "name": "Giulia Ferrari"},
            ],
            "location": "Zoom",
            "is_demo": True,
        }),
        "timestamp": (_NOW + timedelta(hours=5)).isoformat(),
    },
    {
        "source": "demo",
        "title": "Investor call — Seed round",
        "priority": 3,
        "metadata": json.dumps({
            "start": (_NOW + timedelta(days=1, hours=3)).isoformat(),
            "end": (_NOW + timedelta(days=1, hours=4)).isoformat(),
            "attendees": [
                {"email": "luca.bianchi@investor.vc", "name": "Luca Bianchi"},
            ],
            "location": "Phone",
            "is_demo": True,
        }),
        "timestamp": (_NOW + timedelta(days=1, hours=3)).isoformat(),
    },
]

DEMO_PROPOSALS: list[dict[str, Any]] = [
    {
        "type": "email_reply",
        "title": "Reply to Marco Rossi's follow-up",
        "description": "Marco is waiting for a response about the Q1 proposal. Suggested reply drafted.",
        "priority": 3,
        "status": "pending",
        "metadata": json.dumps({
            "suggested_action": "reply",
            "contact": "marco.rossi@acmecorp.com",
            "is_demo": True,
        }),
    },
    {
        "type": "task",
        "title": "Process overdue invoice #2024-089",
        "description": "Invoice for €2,400 is 7 days overdue. Action needed to avoid service disruption.",
        "priority": 4,
        "status": "pending",
        "metadata": json.dumps({"is_demo": True}),
    },
    {
        "type": "follow_up",
        "title": "Send cap table to Luca Bianchi",
        "description": "Investor is interested and waiting for the cap table. Strike while the iron is hot.",
        "priority": 3,
        "status": "pending",
        "metadata": json.dumps({"contact": "luca.bianchi@investor.vc", "is_demo": True}),
    },
]

DEMO_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern_type": "weekly_habit",
        "description": "Every Monday you search for 'standup notes' — consider automating weekly prep.",
        "occurrences": 8,
        "confidence": 0.92,
    },
    {
        "pattern_type": "response_gap",
        "description": "Marco Rossi hasn't received a reply in 5 days — relationship at risk.",
        "occurrences": 1,
        "confidence": 0.75,
    },
    {
        "pattern_type": "cost_optimization",
        "description": "3 unused SaaS subscriptions detected: €34/month potential saving.",
        "occurrences": 3,
        "confidence": 0.85,
    },
    {
        "pattern_type": "focus_time",
        "description": "You're most productive 09:00–11:00. 4 meetings scheduled in this window this week.",
        "occurrences": 4,
        "confidence": 0.88,
    },
    {
        "pattern_type": "topic_trend",
        "description": "Pricing discussions up 40% this week — possible deal acceleration.",
        "occurrences": 6,
        "confidence": 0.70,
    },
]

DEMO_MEMORIES: list[dict[str, Any]] = [
    {"text": "Marco Rossi from Acme Corp is interested in the Q1 proposal. Last contact: 5 days ago.", "source": "demo", "source_type": "demo"},
    {"text": "Giulia Ferrari at Startup.io reported export function crash on large datasets.", "source": "demo", "source_type": "demo"},
    {"text": "Luca Bianchi (Bianchi Ventures) is considering a €300K-500K seed investment.", "source": "demo", "source_type": "demo"},
    {"text": "Engineering sprint kicked off Monday. Beta target is March 15.", "source": "demo", "source_type": "demo"},
    {"text": "Weekly standup notes are searched every Monday morning.", "source": "demo", "source_type": "demo"},
    {"text": "Sofia Ricci delivered the new design system mockups. Review pending.", "source": "demo", "source_type": "demo"},
    {"text": "Invoice #2024-089 from supplier overdue by 7 days: €2,400.", "source": "demo", "source_type": "demo"},
]


# ─────────────────────────────────────────────────────────────────────────────
# Manager
# ─────────────────────────────────────────────────────────────────────────────

class DemoDataManager:
    """Manages demo mode: activation, deactivation, state detection."""

    PREF_KEY = "demo_mode_active"

    def __init__(self, db: Any, memory: Any = None) -> None:
        self._db = db
        self._memory = memory

    def is_active(self) -> bool:
        """Return True if demo mode is currently activated."""
        try:
            return bool(self._db.get_preference(self.PREF_KEY, ""))
        except Exception:
            return False

    def should_auto_activate(self) -> bool:
        """Return True if demo data should be auto-activated.

        Auto-activates when there is no real data (events + contacts = 0)
        and demo mode hasn't been explicitly disabled.
        """
        try:
            explicit = self._db.get_preference("demo_mode_disabled", "")
            if explicit:
                return False
            stats = self._db.get_stats()
            real_events = stats.get("events", 0)
            real_contacts = stats.get("contacts", 0)
            return (real_events + real_contacts) == 0
        except Exception:
            return False

    def activate(self) -> int:
        """Insert all demo records. Returns count of records inserted."""
        from omnibrain.models import ContactInfo, Observation

        logger.info("Activating demo mode")
        count = 0

        # Contacts
        for c in DEMO_CONTACTS:
            try:
                contact = ContactInfo(
                    email=c["email"],
                    name=c["name"],
                    relationship=c["relationship"],
                    organization=c["organization"],
                    interaction_count=c.get("interaction_count", 0),
                )
                self._db.upsert_contact(contact)
                count += 1
            except Exception as e:
                logger.debug("Demo contact insert failed: %s", e)

        # Emails (as events)
        for ev in DEMO_EMAILS:
            try:
                meta = ev.get("metadata", {})
                if isinstance(meta, str):
                    import json as _json
                    meta = _json.loads(meta)
                self._db.insert_event(
                    source=ev["source"],
                    event_type="email",
                    title=ev["title"],
                    content="",
                    metadata=meta,
                    priority=ev.get("priority", 0),
                    timestamp=ev.get("timestamp"),
                )
                count += 1
            except Exception as e:
                logger.debug("Demo email insert failed: %s", e)

        # Calendar (as events)
        for ev in DEMO_CALENDAR:
            try:
                meta = ev.get("metadata", {})
                if isinstance(meta, str):
                    import json as _json
                    meta = _json.loads(meta)
                self._db.insert_event(
                    source=ev["source"],
                    event_type="meeting",
                    title=ev["title"],
                    content="",
                    metadata=meta,
                    priority=ev.get("priority", 0),
                    timestamp=ev.get("timestamp"),
                )
                count += 1
            except Exception as e:
                logger.debug("Demo calendar insert failed: %s", e)

        # Proposals
        for p in DEMO_PROPOSALS:
            try:
                self._db.insert_proposal(
                    type=p["type"],
                    title=p["title"],
                    description=p["description"],
                    priority=p.get("priority", 2),
                )
                count += 1
            except Exception as e:
                logger.debug("Demo proposal insert failed: %s", e)

        # Patterns / observations
        for obs in DEMO_PATTERNS:
            try:
                observation = Observation(
                    type=obs.get("pattern_type", "demo"),
                    detail=obs.get("description", ""),
                    confidence=obs.get("confidence", 0.7),
                    frequency=obs.get("occurrences", 1),
                )
                self._db.insert_observation(observation)
                count += 1
            except Exception as e:
                logger.debug("Demo observation insert failed: %s", e)

        # Memories
        if self._memory:
            for m in DEMO_MEMORIES:
                try:
                    self._memory.store(
                        text=m["text"],
                        source=m["source"],
                        source_type=m["source_type"],
                    )
                    count += 1
                except Exception as e:
                    logger.debug("Demo memory insert failed: %s", e)

        # Mark as active
        try:
            self._db.set_preference(self.PREF_KEY, "1", learned_from="demo")
        except Exception:
            pass

        logger.info("Demo mode activated: %d records inserted", count)
        return count

    def deactivate(self) -> int:
        """Remove all demo records. Returns count of records removed."""
        logger.info("Deactivating demo mode")
        count = 0

        # Remove demo events
        try:
            with self._db._connect() as conn:
                cursor = conn.execute("DELETE FROM events WHERE source = 'demo'")
                count += cursor.rowcount
        except Exception as e:
            logger.debug("Demo event removal failed: %s", e)

        # Remove demo contacts (only those with zero real interactions after removal)
        # Safe approach: remove by known emails
        for c in DEMO_CONTACTS:
            try:
                with self._db._connect() as conn:
                    cursor = conn.execute(
                        "DELETE FROM contacts WHERE email = ?", (c["email"],)
                    )
                    count += cursor.rowcount
            except Exception as e:
                logger.debug("Demo contact removal failed: %s", e)

        # Remove demo proposals
        try:
            with self._db._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM proposals WHERE metadata LIKE '%is_demo%' AND metadata LIKE '%true%'"
                )
                count += cursor.rowcount
        except Exception as e:
            logger.debug("Demo proposal removal failed: %s", e)

        # Remove demo observations
        try:
            with self._db._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM observations WHERE description IN ({})"
                    .format(",".join("?" for _ in DEMO_PATTERNS)),
                    [obs["description"] for obs in DEMO_PATTERNS],
                )
                count += cursor.rowcount
        except Exception as e:
            logger.debug("Demo observation removal failed: %s", e)

        # Remove demo memories
        if self._memory:
            try:
                for m in DEMO_MEMORIES:
                    self._memory.delete_by_source("demo")
                    break  # delete_by_source handles all at once
            except Exception as e:
                logger.debug("Demo memory removal failed: %s", e)

        # Mark as inactive + remember user explicit preference
        try:
            self._db.set_preference(self.PREF_KEY, "", learned_from="demo")
            self._db.set_preference("demo_mode_disabled", "1", learned_from="demo")
        except Exception:
            pass

        logger.info("Demo mode deactivated: %d records removed", count)
        return count

    def get_status(self) -> dict[str, Any]:
        """Return demo mode status dict for API responses."""
        return {
            "active": self.is_active(),
            "record_count": len(DEMO_CONTACTS) + len(DEMO_EMAILS) + len(DEMO_CALENDAR) + len(DEMO_PROPOSALS) + len(DEMO_PATTERNS),
            "contacts": len(DEMO_CONTACTS),
            "events": len(DEMO_EMAILS) + len(DEMO_CALENDAR),
            "proposals": len(DEMO_PROPOSALS),
            "patterns": len(DEMO_PATTERNS),
        }
