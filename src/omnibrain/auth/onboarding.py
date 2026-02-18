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

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    # Raw data for persistence — previously discarded
    raw_emails: list[Any] = field(default_factory=list)
    raw_events: list[Any] = field(default_factory=list)
    raw_contacts: set[str] = field(default_factory=set)


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
            completed_at=datetime.now(UTC).isoformat(),
            duration_ms=duration_ms,
            raw_emails=emails,
            raw_events=events,
            raw_contacts=contacts,
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

    async def analyze_streaming(self) -> AsyncIterator[dict[str, Any]]:
        """Run analysis with SSE-compatible progress events.

        Yields dicts suitable for JSON serialization:
          {"type": "progress", "step": "emails", "message": "..."}
          {"type": "progress", "step": "contacts", "count": 12, ...}
          {"type": "insight", "icon": "...", "title": "...", "body": "...", ...}
          {"type": "result", ...full OnboardingResult as dict...}

        Email and calendar fetches run in parallel via asyncio.
        """
        t0 = time.monotonic()
        loop = asyncio.get_running_loop()

        yield {"type": "progress", "step": "start", "message": "Starting analysis..."}

        # ── Parallel fetch: Gmail + Calendar ──
        async def fetch_emails() -> tuple[list[Any], str]:
            def _sync() -> tuple[list[Any], str]:
                try:
                    from omnibrain.integrations.gmail import GmailClient
                    gmail = GmailClient(self._data_dir)
                    if gmail.authenticate():
                        msgs = gmail.fetch_recent(max_results=100, since_hours=168)
                        return msgs, gmail.user_email
                except Exception as e:
                    logger.warning("Streaming onboarding: Gmail failed: %s", e)
                return [], ""
            return await loop.run_in_executor(None, _sync)

        async def fetch_events() -> list[Any]:
            def _sync() -> list[Any]:
                try:
                    from omnibrain.integrations.calendar import CalendarClient
                    cal = CalendarClient(self._data_dir)
                    if cal.authenticate():
                        return cal.get_upcoming_events(days=7, max_results=50)
                except Exception as e:
                    logger.warning("Streaming onboarding: Calendar failed: %s", e)
                return []
            return await loop.run_in_executor(None, _sync)

        yield {"type": "progress", "step": "emails", "message": "Reading your emails..."}

        # Launch both in parallel
        email_task = asyncio.create_task(fetch_emails())
        calendar_task = asyncio.create_task(fetch_events())

        emails, user_email = await email_task
        email_count = len(emails)

        yield {
            "type": "progress",
            "step": "emails",
            "count": email_count,
            "message": f"Found {email_count} emails from the last 7 days",
        }

        # ── Extract contacts ──
        yield {"type": "progress", "step": "contacts", "message": "Mapping your contacts..."}

        contacts: set[str] = set()
        for em in emails:
            if hasattr(em, "sender") and em.sender:
                contacts.add(_extract_email(em.sender))
            if hasattr(em, "recipients"):
                for r in em.recipients:
                    contacts.add(_extract_email(r))

        events = await calendar_task
        event_count = len(events)

        yield {
            "type": "progress",
            "step": "calendar",
            "count": event_count,
            "message": f"Found {event_count} events this week",
        }

        # Add attendees as contacts
        for ev in events:
            if hasattr(ev, "attendees"):
                for a in ev.attendees:
                    contacts.add(_extract_email(a))

        contacts.discard("")
        contacts.discard(user_email)
        contact_count = len(contacts)

        yield {
            "type": "progress",
            "step": "contacts",
            "count": contact_count,
            "message": f"Mapped {contact_count} people in your network",
        }

        # ── Generate insights ──
        yield {"type": "progress", "step": "insights", "message": "Generating insights..."}

        user_name = _guess_name_from_email(user_email)
        greeting = _build_greeting(user_name)
        insights = _generate_insights(
            emails=emails,
            events=events,
            contacts=contacts,
            email_count=email_count,
            event_count=event_count,
        )
        insights_sorted = sorted(insights, key=lambda c: -c.priority)

        # Stream each insight card individually
        for card in insights_sorted:
            yield {
                "type": "insight",
                "icon": card.icon,
                "title": card.title,
                "body": card.body,
                "action": card.action,
                "action_type": card.action_type,
                "priority": card.priority,
            }
            await asyncio.sleep(0.15)  # stagger for smooth frontend animation

        duration_ms = int((time.monotonic() - t0) * 1000)

        # ── Final result event ──
        yield {
            "type": "result",
            "greeting": greeting,
            "stats": {
                "emails": email_count,
                "contacts": contact_count,
                "events": event_count,
            },
            "insights": [
                {
                    "icon": c.icon,
                    "title": c.title,
                    "body": c.body,
                    "action": c.action,
                    "action_type": c.action_type,
                    "priority": c.priority,
                }
                for c in insights_sorted
            ],
            "user_email": user_email,
            "user_name": user_name,
            "completed_at": datetime.now(UTC).isoformat(),
            "duration_ms": duration_ms,
        }

        logger.info(
            "Streaming onboarding complete in %dms: %d emails, %d contacts, %d events, %d insights",
            duration_ms, email_count, contact_count, event_count, len(insights_sorted),
        )


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
    """Generate 3-7 insight cards from the fetched data.

    Each card uses emotive "WTF" micro-copy designed to make the user
    feel the AI already knows them deeply. All analysis is local — zero
    LLM calls for speed.
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
                    "That's your #1 correspondent this week. "
                    "I'll remember every conversation so you never lose context."
                ),
                action="Ask me what they said",
                action_type="draft_email",
                priority=3,
            ))

    # ── Unanswered emails > 48h ──
    if emails:
        unanswered = _detect_unanswered_emails(emails)
        if unanswered:
            count = len(unanswered)
            oldest_sender = _extract_display_name(unanswered[0].get("sender", "someone"))
            days = unanswered[0].get("days_ago", 2)
            cards.append(InsightCard(
                icon="alert",
                title=f"{count} email{'s' if count > 1 else ''} waiting for your reply",
                body=(
                    f"{oldest_sender} wrote {days} days ago and you haven't replied yet. "
                    f"Want me to draft a response?"
                ),
                action="See draft reply",
                action_type="draft_email",
                priority=6,
            ))

    # ── Upcoming meeting load ──
    if events:
        today_events = [
            e for e in events
            if hasattr(e, "start_time") and _is_today(e.start_time)
        ]
        if today_events:
            first_title = today_events[0].title if hasattr(today_events[0], "title") else "meeting"
            total_minutes = _sum_meeting_minutes(today_events)
            hours = total_minutes // 60
            mins = total_minutes % 60
            time_str = f"{hours}h{mins:02d}m" if hours else f"{mins}m"
            cards.append(InsightCard(
                icon="calendar",
                title=f"{len(today_events)} meeting{'s' if len(today_events) != 1 else ''} today ({time_str})",
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

    # ── Tomorrow's meeting density ──
    if events:
        tomorrow_events = [
            e for e in events
            if hasattr(e, "start_time") and _is_tomorrow(e.start_time)
        ]
        if len(tomorrow_events) >= 3:
            total_minutes = _sum_meeting_minutes(tomorrow_events)
            hours = total_minutes / 60
            cards.append(InsightCard(
                icon="calendar",
                title=f"Tomorrow: {len(tomorrow_events)} meetings, {hours:.1f}h blocked",
                body=(
                    "Heads up — your tomorrow is packed. "
                    "I'll prepare briefs for each one tonight."
                ),
                action="See tomorrow's brief",
                action_type="view_event",
                priority=4,
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

    # ── Subscription detection ──
    if emails:
        subscriptions = _detect_subscriptions(emails)
        if subscriptions:
            sub_names = ", ".join(s["name"] for s in subscriptions[:3])
            total = len(subscriptions)
            cards.append(InsightCard(
                icon="trend",
                title=f"I found {total} subscription{'s' if total > 1 else ''}: {sub_names}",
                body=(
                    "I can track these and alert you before they renew. "
                    "No more surprise charges."
                ),
                action="Review subscriptions",
                action_type="add_skill",
                priority=2,
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

    return cards[:7]


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
        now = datetime.now(UTC)
        if hasattr(dt, "date"):
            return dt.date() == now.date()
    except Exception:
        pass
    return False


def _is_tomorrow(dt: Any) -> bool:
    """Check if a datetime is tomorrow."""
    try:
        from datetime import timedelta
        tomorrow = datetime.now(UTC).date() + timedelta(days=1)
        if hasattr(dt, "date"):
            return dt.date() == tomorrow
    except Exception:
        pass
    return False


def _sum_meeting_minutes(events: list[Any]) -> int:
    """Sum the total meeting duration in minutes."""
    total = 0
    for ev in events:
        start = getattr(ev, "start_time", None) or getattr(ev, "start", None)
        end = getattr(ev, "end_time", None) or getattr(ev, "end", None)
        if start and end and hasattr(start, "timestamp") and hasattr(end, "timestamp"):
            try:
                delta = (end - start).total_seconds() / 60
                total += max(0, int(delta))
            except Exception:
                total += 30  # default 30min
        else:
            total += 30
    return total


def _detect_unanswered_emails(emails: list[Any]) -> list[dict[str, Any]]:
    """Detect emails that may need a reply (> 48h old, not from the user).

    Returns list of dicts with sender and days_ago.
    """
    from datetime import timedelta

    unanswered: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=48)

    # Track which senders we've already replied to
    replied_to: set[str] = set()
    sent_subjects: set[str] = set()

    for em in emails:
        if getattr(em, "is_sent", False) or getattr(em, "label_sent", False):
            subject = (getattr(em, "subject", "") or "").lower().strip()
            if subject.startswith("re:"):
                sent_subjects.add(subject[3:].strip())
            sender = _extract_email(getattr(em, "sender", ""))
            replied_to.add(sender)

    for em in emails:
        if getattr(em, "is_sent", False) or getattr(em, "label_sent", False):
            continue

        sender = getattr(em, "sender", "")
        sender_email = _extract_email(sender)
        if sender_email in replied_to:
            continue

        # Check age
        ts = getattr(em, "date", None) or getattr(em, "timestamp", None)
        if ts and hasattr(ts, "timestamp"):
            try:
                if ts.replace(tzinfo=UTC if ts.tzinfo is None else ts.tzinfo) < cutoff:
                    days_ago = (now - ts.replace(
                        tzinfo=UTC if ts.tzinfo is None else ts.tzinfo
                    )).days
                    subject = (getattr(em, "subject", "") or "").lower().strip()
                    if subject not in sent_subjects:
                        unanswered.append({
                            "sender": sender,
                            "days_ago": max(days_ago, 2),
                            "subject": getattr(em, "subject", ""),
                        })
            except Exception:
                pass

    # Deduplicate by sender, keep oldest
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in sorted(unanswered, key=lambda x: -x["days_ago"]):
        key = _extract_email(item["sender"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:5]


# Common subscription senders/domains
_SUBSCRIPTION_INDICATORS = {
    "netflix", "spotify", "amazon prime", "apple", "disney+",
    "hulu", "adobe", "microsoft 365", "dropbox", "slack",
    "notion", "figma", "canva", "grammarly", "duolingo",
    "nytimes", "medium", "substack", "patreon",
    "billing", "invoice", "subscription", "renewal",
    "your payment", "receipt", "auto-renew",
}


def _detect_subscriptions(emails: list[Any]) -> list[dict[str, str]]:
    """Detect subscription services from email subjects and senders.

    Returns list of dicts with `name` key.
    """
    found: dict[str, str] = {}

    for em in emails:
        sender = (getattr(em, "sender", "") or "").lower()
        subject = (getattr(em, "subject", "") or "").lower()
        combined = sender + " " + subject

        for indicator in _SUBSCRIPTION_INDICATORS:
            if indicator in combined:
                # Extract service name
                name = _guess_service_name(sender, subject, indicator)
                if name and name not in found:
                    found[name] = indicator
                    break

    return [{"name": name} for name in sorted(found)][:10]


def _guess_service_name(sender: str, subject: str, indicator: str) -> str:
    """Guess a clean service name from email metadata."""
    # Known services
    known = {
        "netflix": "Netflix", "spotify": "Spotify",
        "amazon prime": "Amazon Prime", "apple": "Apple",
        "disney+": "Disney+", "hulu": "Hulu",
        "adobe": "Adobe", "microsoft 365": "Microsoft 365",
        "dropbox": "Dropbox", "slack": "Slack",
        "notion": "Notion", "figma": "Figma",
        "canva": "Canva", "grammarly": "Grammarly",
        "duolingo": "Duolingo", "medium": "Medium",
    }
    if indicator in known:
        return known[indicator]

    # Extract from sender domain
    if "@" in sender:
        domain = sender.split("@")[1].split(".")[0]
        if len(domain) > 2:
            return domain.capitalize()

    return ""
