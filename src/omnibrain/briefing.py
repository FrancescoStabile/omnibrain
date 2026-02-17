"""
OmniBrain — Morning Briefing Engine

Generates comprehensive morning briefings by pulling together all
available data: emails, calendar events, pending proposals, observations.

The briefing follows the manifesto's "Magic Moment #1" format:
    1. Overnight email summary (count, urgent, drafts ready)
    2. Today's calendar (meetings, conflicts, prep needed)
    3. Pending proposals (actions waiting for approval)
    4. Top priorities (AI-generated based on urgency + deadline)
    5. Patterns detected overnight

This can be called:
    - Automatically at scheduled time (via proactive engine)
    - On demand via CLI: `omnibrain briefing`
    - Via API: GET /api/v1/briefing
    - Via Telegram: /briefing
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from omnibrain.models import Briefing, BriefingType

logger = logging.getLogger("omnibrain.briefing")


# ═══════════════════════════════════════════════════════════════════════════
# Briefing Data Sections
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class EmailSection:
    """Email summary for the briefing."""
    total: int = 0
    unread: int = 0
    urgent: int = 0
    needs_response: int = 0
    drafts_ready: int = 0
    top_senders: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "unread": self.unread,
            "urgent": self.urgent,
            "needs_response": self.needs_response,
            "drafts_ready": self.drafts_ready,
            "top_senders": self.top_senders,
        }


@dataclass
class CalendarSection:
    """Calendar summary for the briefing."""
    total_events: int = 0
    total_hours: float = 0.0
    next_meeting: str = ""
    next_meeting_time: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "total_hours": self.total_hours,
            "next_meeting": self.next_meeting,
            "next_meeting_time": self.next_meeting_time,
            "events": self.events,
            "conflicts": self.conflicts,
        }


@dataclass
class ProposalSection:
    """Pending proposals for the briefing."""
    total_pending: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    high_priority: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_pending": self.total_pending,
            "by_type": self.by_type,
            "high_priority": self.high_priority,
        }


@dataclass
class PriorityItem:
    """A priority item for today."""
    rank: int
    title: str
    reason: str
    source: str = ""  # "email", "calendar", "proposal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "title": self.title,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass
class BriefingData:
    """Complete data for generating a briefing."""
    date: str = ""
    briefing_type: str = BriefingType.MORNING.value
    emails: EmailSection = field(default_factory=EmailSection)
    calendar: CalendarSection = field(default_factory=CalendarSection)
    proposals: ProposalSection = field(default_factory=ProposalSection)
    priorities: list[PriorityItem] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    memory_highlights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "briefing_type": self.briefing_type,
            "emails": self.emails.to_dict(),
            "calendar": self.calendar.to_dict(),
            "proposals": self.proposals.to_dict(),
            "priorities": [p.to_dict() for p in self.priorities],
            "observations": self.observations,
            "memory_highlights": self.memory_highlights,
        }

    @property
    def events_processed(self) -> int:
        return self.emails.total + self.calendar.total_events

    @property
    def actions_proposed(self) -> int:
        return self.proposals.total_pending


# ═══════════════════════════════════════════════════════════════════════════
# Briefing Generator
# ═══════════════════════════════════════════════════════════════════════════


class BriefingGenerator:
    """Generates morning/evening/weekly briefings.

    Pulls data from the database and memory system, assembles sections,
    formats into human-readable output. When an LLM router is provided,
    generates a rich narrative briefing; otherwise falls back to heuristic
    formatting.

    Usage:
        gen = BriefingGenerator(db, memory_manager, router=router)
        data = gen.collect_data(briefing_type="morning")
        text = gen.format_text(data)
        gen.store(data, text)
    """

    def __init__(self, db: Any, memory_manager: Any = None, router: Any = None):
        """
        Args:
            db: OmniBrainDB instance.
            memory_manager: Optional MemoryManager for memory highlights.
            router: Optional LLMRouter for narrative briefing generation.
        """
        self._db = db
        self._memory = memory_manager
        self._router = router

    def generate(self, briefing_type: str = "morning") -> tuple[BriefingData, str]:
        """Generate a complete briefing. Returns (data, formatted_text).

        Uses heuristic formatting. For LLM-powered narrative,
        use ``generate_narrative()`` instead.
        """
        data = self.collect_data(briefing_type)
        text = self.format_text(data)
        return data, text

    async def generate_narrative(self, briefing_type: str = "morning") -> tuple[BriefingData, str]:
        """Generate a briefing with LLM narrative if a router is available.

        Falls back to heuristic formatting when no router is configured.
        Returns (data, formatted_text).
        """
        data = self.collect_data(briefing_type)

        if self._router and self._has_meaningful_data(data):
            try:
                narrative = await self._llm_format(data)
                if narrative and len(narrative) > 50:
                    return data, narrative
            except Exception as e:
                logger.warning("LLM briefing generation failed, falling back: %s", e)

        text = self.format_text(data)
        return data, text

    def _has_meaningful_data(self, data: BriefingData) -> bool:
        """Check if there's enough data to warrant an LLM call."""
        return any([
            data.emails.total > 0,
            data.calendar.total_events > 0,
            data.proposals.total_pending > 0,
            data.priorities,
            data.observations,
            data.memory_highlights,
        ])

    async def _llm_format(self, data: BriefingData) -> str:
        """Use the LLM to generate a warm, narrative briefing."""
        import asyncio

        user_name = ""
        try:
            user_name = self._db.get_preference("user_name", "")
        except Exception:
            pass

        # Build a structured prompt with all available data
        sections = []

        if data.emails.total > 0:
            sections.append(
                f"EMAILS: {data.emails.total} total, {data.emails.unread} unread, "
                f"{data.emails.urgent} urgent, {data.emails.needs_response} need response. "
                f"Top senders: {', '.join(data.emails.top_senders[:3]) if data.emails.top_senders else 'none'}."
            )

        if data.calendar.total_events > 0:
            events_desc = []
            for ev in data.calendar.events[:5]:
                events_desc.append(f"  - {ev.get('time', '')} {ev.get('title', '')} ({ev.get('attendees', 0)} attendees)")
            section = f"CALENDAR: {data.calendar.total_events} events today ({data.calendar.total_hours:.1f}h)."
            if data.calendar.next_meeting:
                section += f" Next: {data.calendar.next_meeting} at {data.calendar.next_meeting_time}."
            if events_desc:
                section += "\n" + "\n".join(events_desc)
            sections.append(section)

        if data.proposals.total_pending > 0:
            sections.append(
                f"PENDING ACTIONS: {data.proposals.total_pending} proposals waiting for approval."
            )

        if data.priorities:
            pri_desc = [f"  {p.rank}. {p.title} — {p.reason}" for p in data.priorities[:5]]
            sections.append("PRIORITIES:\n" + "\n".join(pri_desc))

        if data.observations:
            sections.append("PATTERNS: " + "; ".join(data.observations[:3]))

        if data.memory_highlights:
            sections.append("WHAT I REMEMBER:\n" + "\n".join(f"  - {h}" for h in data.memory_highlights[:5]))

        data_block = "\n\n".join(sections) if sections else "No data available yet."

        system = (
            "You are OmniBrain, a warm personal AI companion. "
            "Generate a concise morning briefing from the data below. "
            "Be warm but efficient. Use markdown. "
            "Include only sections that have data. "
            "If there's conversation memory but no email/calendar, "
            "focus on what the user shared and what's ahead for them. "
            "Keep it under 300 words. Don't invent data."
        )

        prompt = (
            f"Today: {data.date}\n"
            f"User: {user_name or 'there'}\n"
            f"Type: {data.briefing_type}\n\n"
            f"DATA:\n{data_block}\n\n"
            "Generate the briefing."
        )

        response = ""
        async for chunk in self._router.stream(
            messages=[{"role": "user", "content": prompt}],
            system=system,
        ):
            if chunk.content:
                response += chunk.content
            if chunk.done:
                break

        return response.strip()

    def generate_and_store(self, briefing_type: str = "morning") -> tuple[BriefingData, str, int]:
        """Generate a briefing and store it in the DB.

        Uses heuristic formatting (sync). For LLM narrative,
        use ``generate_and_store_narrative()`` instead.

        Returns:
            Tuple of (data, formatted_text, briefing_id).
        """
        data, text = self.generate(briefing_type)
        briefing_id = self.store(data, text)
        return data, text, briefing_id

    async def generate_and_store_narrative(self, briefing_type: str = "morning") -> tuple[BriefingData, str, int]:
        """Generate a briefing with LLM narrative and store it.

        Falls back to heuristic if no router or LLM fails.

        Returns:
            Tuple of (data, formatted_text, briefing_id).
        """
        data, text = await self.generate_narrative(briefing_type)
        briefing_id = self.store(data, text)
        return data, text, briefing_id

    def collect_data(self, briefing_type: str = "morning") -> BriefingData:
        """Collect all data for a briefing.

        Queries the database for emails, events, proposals, observations,
        and user context from conversations.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        data = BriefingData(date=today, briefing_type=briefing_type)

        # Emails
        data.emails = self._collect_emails()

        # Calendar (Google + chat-extracted events)
        data.calendar = self._collect_calendar()

        # Proposals
        data.proposals = self._collect_proposals()

        # Observations
        data.observations = self._collect_observations()

        # Memory highlights (conversations + profile + observations)
        if self._memory:
            data.memory_highlights = self._collect_memory_highlights()

        # Generate priorities from collected data
        data.priorities = self._generate_priorities(data)

        logger.info(
            f"Briefing data collected: {data.emails.total} emails, "
            f"{data.calendar.total_events} events, "
            f"{data.proposals.total_pending} proposals, "
            f"{len(data.priorities)} priorities"
        )

        return data

    def format_text(self, data: BriefingData) -> str:
        """Format briefing data into human-readable text.

        Produces Markdown suitable for Telegram, CLI, and API.
        """
        lines = []
        today = data.date or datetime.now().strftime("%Y-%m-%d")

        title = {
            "morning": "🔔 Morning Briefing",
            "evening": "🌙 Evening Summary",
            "weekly": "📊 Weekly Review",
        }.get(data.briefing_type, "📋 Briefing")

        lines.append(f"**{title} — {today}**\n")

        # ── Email Section ──
        if data.emails.total > 0:
            lines.append("**📧 Email Overview**")
            lines.append(
                f"• {data.emails.total} emails received"
                f" → {data.emails.unread} unread"
            )
            if data.emails.urgent:
                lines.append(f"• ⚠️ {data.emails.urgent} urgent — require attention")
            if data.emails.needs_response:
                lines.append(f"• {data.emails.needs_response} need your response")
            if data.emails.drafts_ready:
                lines.append(f"• ✏️ {data.emails.drafts_ready} draft responses ready")
            if data.emails.top_senders:
                lines.append(f"• Top senders: {', '.join(data.emails.top_senders[:3])}")
            lines.append("")

        # ── Calendar Section ──
        if data.calendar.total_events > 0:
            lines.append("**📅 Today's Calendar**")
            lines.append(
                f"• {data.calendar.total_events} events"
                f" ({data.calendar.total_hours:.1f}h of meetings)"
            )
            if data.calendar.next_meeting:
                lines.append(
                    f"• Next: {data.calendar.next_meeting}"
                    f" at {data.calendar.next_meeting_time}"
                )
            for event in data.calendar.events[:5]:
                time_str = event.get("time", "")
                title = event.get("title", "")
                attendees = event.get("attendees", 0)
                lines.append(f"  - {time_str} {title} ({attendees} attendees)")
            if data.calendar.conflicts:
                for conflict in data.calendar.conflicts:
                    lines.append(f"  ⚠️ Conflict: {conflict}")
            lines.append("")

        # ── Proposals Section ──
        if data.proposals.total_pending > 0:
            lines.append("**🎯 Pending Actions**")
            lines.append(f"• {data.proposals.total_pending} actions waiting for approval")
            for item in data.proposals.high_priority[:3]:
                lines.append(f"  - [{item.get('type', '')}] {item.get('title', '')}")
            lines.append("")

        # ── Priorities ──
        if data.priorities:
            lines.append("**🏆 Top Priorities Today**")
            for p in data.priorities[:5]:
                lines.append(f"{p.rank}. {p.title}")
                if p.reason:
                    lines.append(f"   _{p.reason}_")
            lines.append("")

        # ── Observations ──
        if data.observations:
            lines.append("**💡 Patterns Detected**")
            for obs in data.observations[:3]:
                lines.append(f"• {obs}")
            lines.append("")

        # ── Memory Highlights ──
        if data.memory_highlights:
            lines.append("**🧠 Memory Notes**")
            for hl in data.memory_highlights[:3]:
                lines.append(f"• {hl}")
            lines.append("")

        # ── Footer ──
        if not any([
            data.emails.total, data.calendar.total_events,
            data.proposals.total_pending, data.priorities,
            data.memory_highlights,
        ]):
            lines.append("_All quiet today! Chat with me to get started — the more I know about you, the better your briefings get._")

        return "\n".join(lines).strip()

    def store(self, data: BriefingData, text: str) -> int:
        """Store the briefing in the database.

        Returns:
            The briefing ID.
        """
        briefing = Briefing(
            date=data.date or datetime.now().strftime("%Y-%m-%d"),
            type=data.briefing_type,
            content=text,
            events_processed=data.events_processed,
            actions_proposed=data.actions_proposed,
        )
        briefing_id = self._db.insert_briefing(briefing)
        logger.info(f"Stored {data.briefing_type} briefing: id={briefing_id}")
        return briefing_id

    # ── Data Collection Helpers ──

    def _collect_emails(self) -> EmailSection:
        """Collect email data from DB."""
        section = EmailSection()

        try:
            stats = self._db.get_stats()
            section.total = stats.get("events_email", 0)

            # Query last 24h emails from events table
            since_24h = datetime.now() - timedelta(hours=24)
            events = self._db.get_events(source="gmail", since=since_24h, limit=50)

            if events:
                section.total = len(events)
                section.unread = sum(
                    1 for e in events
                    if not _meta_flag(e, "is_read")
                )

                # Count urgent via metadata
                section.urgent = sum(
                    1 for e in events
                    if _meta_str(e, "urgency") in ("critical", "high")
                )

                # Top senders
                senders: dict[str, int] = {}
                for e in events:
                    sender = _meta_str(e, "sender_email") or e.get("title", "")
                    if sender:
                        senders[sender] = senders.get(sender, 0) + 1
                section.top_senders = sorted(senders, key=senders.get, reverse=True)[:5]

            # Drafts ready = proposals of type email_draft with pending status
            pending_proposals = self._db.get_pending_proposals()
            section.drafts_ready = sum(
                1 for p in pending_proposals
                if p.get("type") == "email_draft"
            )
            section.needs_response = section.urgent + section.drafts_ready

        except Exception as e:
            logger.warning(f"Failed to collect email data: {e}")

        return section

    def _collect_calendar(self) -> CalendarSection:
        """Collect calendar data from DB (Google Calendar + chat-extracted)."""
        section = CalendarSection()

        try:
            # Filter to today's events only
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

            # Google Calendar events — today only
            events = self._db.get_events(
                source="calendar", since=today_start, until=today_end, limit=30,
            )

            # Also include chat-extracted events (commitments, meetings, etc.) — today only
            chat_events = self._db.get_events(
                source="chat", since=today_start, until=today_end, limit=20,
            )
            if chat_events:
                # Deduplicate: skip chat events whose title+date already appear
                # in the calendar events (common when extractor shadows a tool action)
                existing = {(e.get("title", "").lower(), e.get("timestamp", "")[:10]) for e in events}
                for ce in chat_events:
                    key = (ce.get("title", "").lower(), ce.get("timestamp", "")[:10])
                    if key not in existing:
                        events.append(ce)
                        existing.add(key)

            if events:
                section.total_events = len(events)

                total_minutes = 0
                now = datetime.now()
                next_meeting_time = None
                event_items = []

                for e in events:
                    duration = _meta_int(e, "duration_minutes")
                    total_minutes += duration

                    start_str = _meta_str(e, "start_time") or e.get("timestamp", "")
                    attendees = _meta_list(e, "attendees")
                    time_display = start_str[11:16] if len(start_str) >= 16 else ""

                    event_items.append({
                        "title": e.get("title", ""),
                        "time": time_display,
                        "attendees": len(attendees),
                        "duration": duration,
                    })

                    # Find next meeting
                    if start_str:
                        try:
                            start_dt = datetime.fromisoformat(start_str)
                            if start_dt > now:
                                if next_meeting_time is None or start_dt < next_meeting_time:
                                    next_meeting_time = start_dt
                                    section.next_meeting = e.get("title", "")
                                    section.next_meeting_time = time_display
                        except (ValueError, TypeError):
                            pass

                section.total_hours = round(total_minutes / 60, 1)
                section.events = event_items

                # Detect conflicts (overlapping events)
                section.conflicts = _detect_conflicts(events)

        except Exception as e:
            logger.warning(f"Failed to collect calendar data: {e}")

        return section

    def _collect_proposals(self) -> ProposalSection:
        """Collect pending proposals from DB."""
        section = ProposalSection()

        try:
            pending = self._db.get_pending_proposals()
            section.total_pending = len(pending)

            for p in pending:
                ptype = p.get("type", "other")
                section.by_type[ptype] = section.by_type.get(ptype, 0) + 1
                if p.get("priority", 2) >= 3:
                    section.high_priority.append({
                        "type": ptype,
                        "title": p.get("title", ""),
                        "priority": p.get("priority", 2),
                    })

        except Exception as e:
            logger.warning(f"Failed to collect proposals: {e}")

        return section

    def _collect_observations(self) -> list[str]:
        """Collect recent observations."""
        try:
            observations = self._db.get_observations(days=30)
            return [
                f"{obs.get('pattern_type', '')}: {obs.get('description', '')}"
                for obs in observations
            ]
        except Exception as e:
            logger.warning(f"Failed to collect observations: {e}")
            return []

    def _collect_memory_highlights(self) -> list[str]:
        """Get relevant memory highlights for the briefing.

        Reads from ALL memory sources: observations, conversations, profile.
        This ensures the briefing has content even without Google integration.
        Conversation entries are cleaned (raw "User: … Assistant: …" stripped)
        and deduplicated.
        """
        if not self._memory:
            return []

        highlights: list[str] = []
        seen: set[str] = set()  # deduplicate by first 80 chars

        def _add(text: str) -> None:
            key = text[:80].lower().strip()
            if key not in seen:
                seen.add(key)
                highlights.append(text)

        try:
            # Observations (pattern-detected insights)
            obs_docs = self._memory.get_recent(max_results=3, source_filter="observation")
            for doc in obs_docs:
                if doc.text:
                    _add(doc.text)

            # Recent conversations — extract what the user said, not raw dumps
            conv_docs = self._memory.get_recent(max_results=5, source_filter="conversation")
            for doc in conv_docs:
                if not doc.text:
                    continue
                text = doc.text.strip()
                # Strip "User: … Assistant: …" format — keep only user's message
                if text.startswith("User:"):
                    parts = text.split("\nAssistant:", 1)
                    user_part = parts[0].removeprefix("User:").strip()
                    if not user_part or len(user_part) < 10:
                        continue
                    text = user_part
                # Trim to digestible length
                if len(text) > 150:
                    text = text[:147].strip() + "…"
                _add(text)

            # User profile (from onboarding)
            profile_docs = self._memory.get_recent(max_results=2, source_filter="profile")
            for doc in profile_docs:
                if doc.text:
                    _add(doc.text)

        except Exception as e:
            logger.warning(f"Failed to collect memory highlights: {e}")

        return highlights

    def _generate_priorities(self, data: BriefingData) -> list[PriorityItem]:
        """Generate AI-style priority list from collected data.

        Uses simple heuristics (not LLM) for now.
        Phase 2: Use the Agent with a plan_template to generate priorities.
        """
        priorities: list[PriorityItem] = []
        rank = 1

        # Urgent emails first
        if data.emails.urgent > 0:
            priorities.append(PriorityItem(
                rank=rank,
                title=f"Respond to {data.emails.urgent} urgent email(s)",
                reason="High urgency — time-sensitive",
                source="email",
            ))
            rank += 1

        # Next meeting prep
        if data.calendar.next_meeting:
            priorities.append(PriorityItem(
                rank=rank,
                title=f"Prepare for: {data.calendar.next_meeting}",
                reason=f"Scheduled at {data.calendar.next_meeting_time}",
                source="calendar",
            ))
            rank += 1

        # High-priority proposals
        for p in data.proposals.high_priority[:2]:
            priorities.append(PriorityItem(
                rank=rank,
                title=p.get("title", "Review proposal"),
                reason="Action required — high priority",
                source="proposal",
            ))
            rank += 1

        # Draft emails
        if data.emails.drafts_ready:
            priorities.append(PriorityItem(
                rank=rank,
                title=f"Review {data.emails.drafts_ready} draft response(s)",
                reason="Draft responses ready for approval",
                source="email",
            ))
            rank += 1

        return priorities[:5]  # Max 5 priorities


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _meta_str(event: dict, key: str) -> str:
    """Get a string from event metadata."""
    meta = event.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (ValueError, TypeError):
            return ""
    if isinstance(meta, dict):
        return str(meta.get(key, ""))
    return ""


def _meta_int(event: dict, key: str) -> int:
    """Get an int from event metadata."""
    val = _meta_str(event, key)
    try:
        return int(val) if val else 0
    except (ValueError, TypeError):
        return 0


def _meta_flag(event: dict, key: str) -> bool:
    """Get a bool from event metadata."""
    val = _meta_str(event, key)
    return val.lower() in ("true", "1", "yes") if val else False


def _meta_list(event: dict, key: str) -> list[str]:
    """Get a list from event metadata."""
    val = _meta_str(event, key)
    if not val:
        return []
    try:
        parsed = json.loads(val)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return [val] if val else []


def _detect_conflicts(events: list[dict]) -> list[str]:
    """Detect overlapping calendar events."""
    conflicts = []
    parsed = []

    for e in events:
        start = _meta_str(e, "start_time")
        end = _meta_str(e, "end_time")
        if start and end:
            try:
                parsed.append({
                    "title": e.get("title", ""),
                    "start": datetime.fromisoformat(start),
                    "end": datetime.fromisoformat(end),
                })
            except (ValueError, TypeError):
                pass

    # Check for overlaps
    for i, a in enumerate(parsed):
        for b in parsed[i + 1:]:
            if a["start"] < b["end"] and b["start"] < a["end"]:
                conflicts.append(f"{a['title']} ↔ {b['title']}")

    return conflicts
