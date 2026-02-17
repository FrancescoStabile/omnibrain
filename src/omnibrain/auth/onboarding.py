"""
OmniBrain — Onboarding Analyzer

Runs the first-time "Holy Shit" analysis after Google OAuth completes.
Connects to Gmail + Calendar, counts data, and produces 3-5 insight
cards — all within ~10 seconds so the frontend animation feels magical.

Usage::

    analyzer = OnboardingAnalyzer(data_dir=Path("~/.omnibrain"))
    result = analyzer.analyze()
    # result.stats → {"emails": 247, "contacts": 12, "events": 8}
    # result.insights → [InsightCard, InsightCard, ...]
    # result.greeting → "Good morning, Francesco."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("omnibrain.auth.onboarding")


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class InsightCard:
    """A single insight surfaced during onboarding."""

    icon: str  # emoji or lucide icon name
    title: str  # short headline
    body: str  # one-sentence description
    action: str = ""  # optional CTA label
    action_type: str = ""  # "draft_email" | "add_skill" | "view_event" | ""
    priority: int = 0  # higher = shown first


@dataclass
class OnboardingResult:
    """Full result of the onboarding analysis."""

    greeting: str = ""
    stats: dict[str, int] = field(default_factory=dict)
    insights: list[InsightCard] = field(default_factory=list)
    user_email: str = ""
    user_name: str = ""
    completed_at: str = ""
    duration_ms: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# Analyzer
# ═══════════════════════════════════════════════════════════════════════════


class OnboardingAnalyzer:
    """Runs first-time analysis to produce the "Holy Shit" moment.

    Fetches 7 days of emails + upcoming calendar events, counts unique
    contacts, generates insight cards, and builds the greeting.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def analyze(self) -> OnboardingResult:
        """Run the full onboarding analysis.

        This is a synchronous call (typically run in a thread pool from
        the async API endpoint). Returns structured results for the
        frontend to animate through.
        """
        import time

        t0 = time.monotonic()

        # ── Fetch Gmail data ──
        emails: list[Any] = []
        email_count = 0
        contacts: set[str] = set()
        user_email = ""

        try:
            from omnibrain.integrations.gmail import GmailClient

            gmail = GmailClient(self._data_dir)
            if gmail.authenticate():
                user_email = gmail.user_email
                emails = gmail.fetch_recent(max_results=100, since_hours=168)  # 7 days
                email_count = len(emails)
                for em in emails:
                    if hasattr(em, "sender") and em.sender:
                        contacts.add(_extract_email(em.sender))
                    if hasattr(em, "recipients"):
                        for r in em.recipients:
                            contacts.add(_extract_email(r))
                contacts.discard("")
                contacts.discard(user_email)
                logger.info("Onboarding: fetched %d emails, %d contacts", email_count, len(contacts))
        except Exception as e:
            logger.warning("Onboarding: Gmail fetch failed: %s", e)

        # ── Fetch Calendar data ──
        events: list[Any] = []
        event_count = 0

        try:
            from omnibrain.integrations.calendar import CalendarClient

            cal = CalendarClient(self._data_dir)
            if cal.authenticate():
                events = cal.get_upcoming_events(days=7, max_results=50)
                event_count = len(events)
                # Extract attendees as additional contacts
                for ev in events:
                    if hasattr(ev, "attendees"):
                        for a in ev.attendees:
                            contacts.add(_extract_email(a))
                contacts.discard("")
                contacts.discard(user_email)
                logger.info("Onboarding: fetched %d events", event_count)
        except Exception as e:
            logger.warning("Onboarding: Calendar fetch failed: %s", e)

        contact_count = len(contacts)

        # ── Greeting ──
        user_name = _guess_name_from_email(user_email)
        greeting = _build_greeting(user_name)

        # ── Generate insights ──
        insights = _generate_insights(
            emails=emails,
            events=events,
            contacts=contacts,
            email_count=email_count,
            event_count=event_count,
        )

        duration_ms = int((time.monotonic() - t0) * 1000)

        result = OnboardingResult(
            greeting=greeting,
            stats={
                "emails": email_count,
                "contacts": contact_count,
                "events": event_count,
            },
            insights=sorted(insights, key=lambda c: -c.priority),
            user_email=user_email,
            user_name=user_name,
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
        )
        logger.info(
            "Onboarding complete in %dms: %d emails, %d contacts, %d events, %d insights",
            duration_ms,
            email_count,
            contact_count,
            event_count,
            len(insights),
        )
        return result


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _extract_email(addr: str) -> str:
    """Extract bare email from 'Name <email>' format."""
    if "<" in addr and ">" in addr:
        return addr.split("<")[1].split(">")[0].strip().lower()
    return addr.strip().lower()


def _guess_name_from_email(email_addr: str) -> str:
    """Best-effort name extraction from email address."""
    if not email_addr:
        return ""
    local = email_addr.split("@")[0]
    # Common patterns: first.last, first_last, firstlast
    parts = local.replace("_", ".").replace("-", ".").split(".")
    return " ".join(p.capitalize() for p in parts if p)


def _build_greeting(name: str) -> str:
    """Build the Reveal screen greeting."""
    hour = datetime.now().hour
    if hour < 12:
        time_greeting = "Good morning"
    elif hour < 18:
        time_greeting = "Good afternoon"
    else:
        time_greeting = "Good evening"

    if name:
        return f"{time_greeting}, {name}."
    return f"{time_greeting}."


def _generate_insights(
    *,
    emails: list[Any],
    events: list[Any],
    contacts: set[str],
    email_count: int,
    event_count: int,
) -> list[InsightCard]:
    """Generate 3-5 insight cards from the fetched data.

    Each card uses emotive "WTF" micro-copy designed to make the user
    feel the AI already knows them deeply.
    """
    cards: list[InsightCard] = []

    # ── Busiest sender ──
    if emails:
        sender_counts: dict[str, int] = {}
        for em in emails:
            sender = getattr(em, "sender", "")
            if sender:
                sender_counts[sender] = sender_counts.get(sender, 0) + 1
        if sender_counts:
            top_sender = max(sender_counts, key=sender_counts.get)  # type: ignore[arg-type]
            top_count = sender_counts[top_sender]
            name = _extract_display_name(top_sender)
            cards.append(InsightCard(
                icon="mail",
                title=f"Did you know? {name} sent you {top_count} emails",
                body=(
                    f"That's your #1 correspondent this week. "
                    f"I'll remember every conversation so you never lose context."
                ),
                action="Ask me what they said",
                action_type="draft_email",
                priority=3,
            ))

    # ── Upcoming meeting load ──
    if events:
        today_events = [
            e for e in events
            if hasattr(e, "start_time") and _is_today(e.start_time)
        ]
        if today_events:
            first_title = today_events[0].title if hasattr(today_events[0], "title") else "meeting"
            cards.append(InsightCard(
                icon="calendar",
                title=f"Heads up — {len(today_events)} meeting{'s' if len(today_events) != 1 else ''} today",
                body=(
                    f"Your next is \"{first_title}\". "
                    f"I already have the context from last time — want a brief?"
                ),
                action="Brief me",
                action_type="view_event",
                priority=5,
            ))
        elif event_count > 0:
            cards.append(InsightCard(
                icon="calendar",
                title=f"{event_count} events this week",
                body=(
                    "Your week is filling up. "
                    "I'll prepare briefs before every meeting so you never walk in cold."
                ),
                action="View schedule",
                action_type="view_event",
                priority=2,
            ))

    # ── Unread ratio ──
    if emails:
        unread = sum(1 for em in emails if not getattr(em, "is_read", True))
        if unread > 5:
            cards.append(InsightCard(
                icon="inbox",
                title=f"You have {unread} unread emails piling up",
                body=(
                    "I can triage them in seconds — surface what's urgent, "
                    "draft replies for what matters, and silence the rest."
                ),
                action="Install Email Manager",
                action_type="add_skill",
                priority=4,
            ))

    # ── Network size ──
    if contacts:
        cards.append(InsightCard(
            icon="users",
            title=f"I mapped {len(contacts)} people in your network",
            body=(
                "I already know who they are and how you interact. "
                "I'll never let you forget a follow-up again."
            ),
            priority=1,
        ))

    # ── Engagement starter (always show at least one insight) ──
    if not cards:
        cards.append(InsightCard(
            icon="sparkles",
            title="I'm learning about you",
            body=(
                "The more we interact, the more useful I become. "
                "Tomorrow morning, I'll surprise you with your first briefing."
            ),
            priority=0,
        ))

    return cards[:5]


def _extract_display_name(sender: str) -> str:
    """Extract display name from 'Name <email>' format."""
    if "<" in sender:
        name = sender.split("<")[0].strip().strip('"')
        if name:
            return name
    return sender


def _is_today(dt: Any) -> bool:
    """Check if a datetime is today (timezone-aware safe)."""
    try:
        now = datetime.now(timezone.utc)
        if hasattr(dt, "date"):
            return dt.date() == now.date()
    except Exception:
        pass
    return False
