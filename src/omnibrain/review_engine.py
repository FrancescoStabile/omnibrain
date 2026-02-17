"""
OmniBrain — Evening Summary + Weekly Review Engine (Day 26-28)

Generates:
    1. Evening Summary — daily recap with stats + tomorrow preview
    2. Weekly Review — 7-day analysis with trends

Architecture:
    ┌─────────────────────────────┐
    │        ReviewEngine         │
    │  ├── generate_evening()     │ → EveningSummary
    │  ├── generate_weekly()      │ → WeeklyReview
    │  └── _compute_stats()       │ → DayStats / WeekStats
    └──────────┬──────────────────┘
               │ reads
    ┌──────────┴──────────────────┐
    │  OmniBrainDB  + MemoryMgr  │
    └─────────────────────────────┘

The engine pulls raw event/proposal/observation data from the DB,
computes aggregate stats, detects trends, and formats human-readable output.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("omnibrain.review_engine")


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DayStats:
    """Aggregated stats for a single day."""

    date: str = ""
    emails_received: int = 0
    emails_classified: int = 0
    drafts_generated: int = 0
    calendar_events: int = 0
    proposals_created: int = 0
    proposals_executed: int = 0
    proposals_rejected: int = 0
    observations_detected: int = 0
    memory_entries_stored: int = 0

    @property
    def actions_taken(self) -> int:
        return self.proposals_executed + self.drafts_generated

    @property
    def total_events_processed(self) -> int:
        return self.emails_received + self.calendar_events

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "emails_received": self.emails_received,
            "emails_classified": self.emails_classified,
            "drafts_generated": self.drafts_generated,
            "calendar_events": self.calendar_events,
            "proposals_created": self.proposals_created,
            "proposals_executed": self.proposals_executed,
            "proposals_rejected": self.proposals_rejected,
            "observations_detected": self.observations_detected,
            "memory_entries_stored": self.memory_entries_stored,
            "actions_taken": self.actions_taken,
            "total_events_processed": self.total_events_processed,
        }


@dataclass
class EveningSummary:
    """Complete evening summary for the day."""

    date: str = ""
    stats: DayStats = field(default_factory=DayStats)
    top_contacts: list[str] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    patterns_detected: list[str] = field(default_factory=list)
    tomorrow_events: list[dict[str, Any]] = field(default_factory=list)
    tomorrow_preview: str = ""
    time_saved_minutes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "stats": self.stats.to_dict(),
            "top_contacts": self.top_contacts,
            "key_decisions": self.key_decisions,
            "patterns_detected": self.patterns_detected,
            "tomorrow_events": self.tomorrow_events,
            "tomorrow_preview": self.tomorrow_preview,
            "time_saved_minutes": self.time_saved_minutes,
        }

    def format_text(self) -> str:
        """Format as human-readable Markdown."""
        lines = [f"**🌙 Evening Summary — {self.date}**\n"]

        # Stats
        s = self.stats
        lines.append("**📊 Today in Numbers**")
        lines.append(f"• {s.total_events_processed} events processed ({s.emails_received} emails, {s.calendar_events} meetings)")
        lines.append(f"• {s.actions_taken} actions taken ({s.proposals_executed} executed, {s.drafts_generated} drafts)")
        if s.observations_detected:
            lines.append(f"• {s.observations_detected} new pattern(s) detected")
        if self.time_saved_minutes > 0:
            lines.append(f"• ⏱️ Estimated time saved: ~{self.time_saved_minutes} min")
        lines.append("")

        # Top contacts
        if self.top_contacts:
            lines.append("**👥 Most Active Contacts**")
            for c in self.top_contacts[:5]:
                lines.append(f"• {c}")
            lines.append("")

        # Key decisions / proposals
        if self.key_decisions:
            lines.append("**✅ Key Decisions**")
            for d in self.key_decisions[:5]:
                lines.append(f"• {d}")
            lines.append("")

        # Patterns
        if self.patterns_detected:
            lines.append("**💡 Patterns Detected**")
            for p in self.patterns_detected[:3]:
                lines.append(f"• {p}")
            lines.append("")

        # Tomorrow
        if self.tomorrow_events:
            lines.append("**📅 Tomorrow Preview**")
            for ev in self.tomorrow_events[:5]:
                time_str = ev.get("time", "")
                title = ev.get("title", "")
                lines.append(f"• {time_str} {title}".strip())
            lines.append("")
        if self.tomorrow_preview:
            lines.append(f"_{self.tomorrow_preview}_")

        return "\n".join(lines).strip()


@dataclass
class WeekStats:
    """Aggregated stats for a week."""

    start_date: str = ""
    end_date: str = ""
    daily_stats: list[DayStats] = field(default_factory=list)

    @property
    def total_emails(self) -> int:
        return sum(d.emails_received for d in self.daily_stats)

    @property
    def total_meetings(self) -> int:
        return sum(d.calendar_events for d in self.daily_stats)

    @property
    def total_actions(self) -> int:
        return sum(d.actions_taken for d in self.daily_stats)

    @property
    def total_observations(self) -> int:
        return sum(d.observations_detected for d in self.daily_stats)

    @property
    def busiest_day(self) -> str:
        if not self.daily_stats:
            return ""
        best = max(self.daily_stats, key=lambda d: d.total_events_processed)
        return best.date

    @property
    def quietest_day(self) -> str:
        if not self.daily_stats:
            return ""
        best = min(self.daily_stats, key=lambda d: d.total_events_processed)
        return best.date

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_emails": self.total_emails,
            "total_meetings": self.total_meetings,
            "total_actions": self.total_actions,
            "total_observations": self.total_observations,
            "busiest_day": self.busiest_day,
            "quietest_day": self.quietest_day,
            "daily_stats": [d.to_dict() for d in self.daily_stats],
        }


@dataclass
class WeeklyReview:
    """Complete weekly review."""

    week_start: str = ""
    week_end: str = ""
    stats: WeekStats = field(default_factory=WeekStats)
    top_contacts: list[str] = field(default_factory=list)
    trends: list[str] = field(default_factory=list)
    observations_summary: list[str] = field(default_factory=list)
    projects_active: list[str] = field(default_factory=list)
    total_time_saved_minutes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start,
            "week_end": self.week_end,
            "stats": self.stats.to_dict(),
            "top_contacts": self.top_contacts,
            "trends": self.trends,
            "observations_summary": self.observations_summary,
            "projects_active": self.projects_active,
            "total_time_saved_minutes": self.total_time_saved_minutes,
        }

    def format_text(self) -> str:
        """Format as human-readable Markdown."""
        lines = [f"**📊 Weekly Review — {self.week_start} → {self.week_end}**\n"]

        s = self.stats

        # Stats overview
        lines.append("**🔢 Week in Numbers**")
        lines.append(f"• {s.total_emails} emails processed")
        lines.append(f"• {s.total_meetings} meetings attended")
        lines.append(f"• {s.total_actions} actions taken")
        if s.total_observations:
            lines.append(f"• {s.total_observations} patterns detected")
        if self.total_time_saved_minutes > 0:
            hours = self.total_time_saved_minutes / 60
            lines.append(f"• ⏱️ Estimated time saved: ~{hours:.1f}h")
        lines.append("")

        # Day distribution
        if s.daily_stats:
            lines.append("**📈 Daily Distribution**")
            for d in s.daily_stats:
                bar = "█" * min(d.total_events_processed, 20)
                lines.append(f"  {d.date[-5:]} {bar} {d.total_events_processed}")
            if s.busiest_day:
                lines.append(f"  📌 Busiest: {s.busiest_day}")
            if s.quietest_day:
                lines.append(f"  📌 Quietest: {s.quietest_day}")
            lines.append("")

        # Trends
        if self.trends:
            lines.append("**📉 Trends**")
            for t in self.trends[:5]:
                lines.append(f"• {t}")
            lines.append("")

        # Top contacts
        if self.top_contacts:
            lines.append("**👥 Top Contacts This Week**")
            for c in self.top_contacts[:5]:
                lines.append(f"• {c}")
            lines.append("")

        # Observations
        if self.observations_summary:
            lines.append("**💡 Patterns & Observations**")
            for o in self.observations_summary[:5]:
                lines.append(f"• {o}")
            lines.append("")

        # Projects
        if self.projects_active:
            lines.append("**🗂️ Active Projects**")
            for p in self.projects_active[:5]:
                lines.append(f"• {p}")
            lines.append("")

        return "\n".join(lines).strip()


# ═══════════════════════════════════════════════════════════════════════════
# Time Estimation Constants
# ═══════════════════════════════════════════════════════════════════════════

# Average minutes saved per automated action
MINUTES_PER_DRAFT = 8        # Writing a reply from scratch
MINUTES_PER_CLASSIFICATION = 1  # Reading + triaging an email
MINUTES_PER_PROPOSAL = 3     # Deciding what to do about something


# ═══════════════════════════════════════════════════════════════════════════
# Review Engine
# ═══════════════════════════════════════════════════════════════════════════


class ReviewEngine:
    """Generates evening summaries and weekly reviews.

    Usage:
        engine = ReviewEngine(db, memory)
        evening = engine.generate_evening()
        text = evening.format_text()

        weekly = engine.generate_weekly()
        text = weekly.format_text()
    """

    def __init__(self, db: Any, memory: Any = None):
        self._db = db
        self._memory = memory

    # ── Evening Summary ──

    def generate_evening(self, date: str | None = None) -> EveningSummary:
        """Generate an evening summary for the given date (default: today)."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        summary = EveningSummary(date=date)

        # Compute today's stats
        summary.stats = self._compute_day_stats(date)

        # Top contacts
        summary.top_contacts = self._get_top_contacts_for_day(date)

        # Key decisions (executed proposals)
        summary.key_decisions = self._get_key_decisions(date)

        # Patterns detected today
        summary.patterns_detected = self._get_patterns_for_day(date)

        # Tomorrow preview
        tomorrow = (datetime.fromisoformat(date) + timedelta(days=1)).strftime("%Y-%m-%d")
        summary.tomorrow_events = self._get_events_for_day(tomorrow)
        summary.tomorrow_preview = self._build_tomorrow_preview(summary.tomorrow_events)

        # Estimate time saved
        summary.time_saved_minutes = self._estimate_time_saved(summary.stats)

        return summary

    # ── Weekly Review ──

    def generate_weekly(self, end_date: str | None = None, days: int = 7) -> WeeklyReview:
        """Generate a weekly review ending on the given date (default: today)."""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        end_dt = datetime.fromisoformat(end_date)
        start_dt = end_dt - timedelta(days=days - 1)
        start_date = start_dt.strftime("%Y-%m-%d")

        review = WeeklyReview(
            week_start=start_date,
            week_end=end_date,
        )

        # Compute daily stats for all 7 days
        daily_stats = []
        for i in range(days):
            d = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            daily_stats.append(self._compute_day_stats(d))

        review.stats = WeekStats(
            start_date=start_date,
            end_date=end_date,
            daily_stats=daily_stats,
        )

        # Top contacts for the week
        review.top_contacts = self._get_top_contacts_for_period(start_date, end_date)

        # Trends
        review.trends = self._detect_trends(daily_stats)

        # Observations summary
        review.observations_summary = self._get_observations_summary(days)

        # Active projects (from context resurrection data if available)
        review.projects_active = self._get_active_projects(days)

        # Total time saved
        review.total_time_saved_minutes = sum(
            self._estimate_time_saved(d) for d in daily_stats
        )

        return review

    # ── Stats Computation ──

    def _compute_day_stats(self, date: str) -> DayStats:
        """Compute aggregated stats for a single day."""
        stats = DayStats(date=date)

        # Parse date range
        day_start = f"{date}T00:00:00"
        since = datetime.fromisoformat(day_start)

        try:
            # Events for the day
            all_events = self._db.get_events(since=since, limit=500)
            day_events = [
                e for e in all_events
                if e.get("timestamp", "").startswith(date)
            ]

            # Count by event type
            for e in day_events:
                etype = e.get("event_type", "")

                if etype == "email_received":
                    stats.emails_received += 1
                elif etype == "calendar_event":
                    stats.calendar_events += 1
                elif etype == "email_classified":
                    stats.emails_classified += 1
                elif etype == "email_draft_generated":
                    stats.drafts_generated += 1

            # Proposals
            proposals = self._db.get_events(
                event_type="proposal_created", since=since, limit=100
            )
            stats.proposals_created = sum(
                1 for p in proposals if p.get("timestamp", "").startswith(date)
            )

            proposals_exec = self._db.get_events(
                event_type="proposal_executed", since=since, limit=100
            )
            stats.proposals_executed = sum(
                1 for p in proposals_exec if p.get("timestamp", "").startswith(date)
            )

            proposals_rej = self._db.get_events(
                event_type="proposal_rejected", since=since, limit=100
            )
            stats.proposals_rejected = sum(
                1 for p in proposals_rej if p.get("timestamp", "").startswith(date)
            )

            # Observations
            observations = self._db.get_observations(days=1)
            stats.observations_detected = sum(
                1 for o in observations
                if o.get("timestamp", "").startswith(date)
            )

            # Memory entries
            if self._memory:
                try:
                    recent = self._memory.get_recent(max_results=200)
                    stats.memory_entries_stored = sum(
                        1 for doc in recent
                        if hasattr(doc, "timestamp") and doc.timestamp
                        and doc.timestamp.startswith(date)
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Failed to compute day stats for {date}: {e}")

        return stats

    def _get_top_contacts_for_day(self, date: str) -> list[str]:
        """Get most active contacts for a given day."""
        since = datetime.fromisoformat(f"{date}T00:00:00")
        contacts: dict[str, int] = {}

        try:
            events = self._db.get_events(since=since, limit=200)
            for e in events:
                if not e.get("timestamp", "").startswith(date):
                    continue
                meta = _parse_meta(e)
                sender = meta.get("sender_email", "")
                if sender:
                    contacts[sender] = contacts.get(sender, 0) + 1
                attendees = meta.get("attendees", [])
                if isinstance(attendees, str):
                    try:
                        attendees = json.loads(attendees)
                    except (ValueError, TypeError):
                        attendees = []
                for a in attendees:
                    if isinstance(a, str) and a:
                        contacts[a] = contacts.get(a, 0) + 1
        except Exception as e:
            logger.warning(f"Failed to get top contacts: {e}")

        sorted_contacts = sorted(contacts.items(), key=lambda x: x[1], reverse=True)
        return [f"{email} ({count})" for email, count in sorted_contacts[:5]]

    def _get_top_contacts_for_period(self, start_date: str, end_date: str) -> list[str]:
        """Get most active contacts over a date range."""
        since = datetime.fromisoformat(f"{start_date}T00:00:00")
        contacts: dict[str, int] = {}

        try:
            events = self._db.get_events(since=since, limit=1000)
            for e in events:
                ts = e.get("timestamp", "")
                if ts < start_date or ts > f"{end_date}T23:59:59":
                    continue
                meta = _parse_meta(e)
                sender = meta.get("sender_email", "")
                if sender:
                    contacts[sender] = contacts.get(sender, 0) + 1
                attendees = meta.get("attendees", [])
                if isinstance(attendees, str):
                    try:
                        attendees = json.loads(attendees)
                    except (ValueError, TypeError):
                        attendees = []
                for a in attendees:
                    if isinstance(a, str) and a:
                        contacts[a] = contacts.get(a, 0) + 1
        except Exception as e:
            logger.warning(f"Failed to get contacts for period: {e}")

        sorted_contacts = sorted(contacts.items(), key=lambda x: x[1], reverse=True)
        return [f"{email} ({count})" for email, count in sorted_contacts[:5]]

    def _get_key_decisions(self, date: str) -> list[str]:
        """Get proposals that were executed today."""
        since = datetime.fromisoformat(f"{date}T00:00:00")
        decisions: list[str] = []

        try:
            events = self._db.get_events(event_type="proposal_executed", since=since, limit=50)
            for e in events:
                if e.get("timestamp", "").startswith(date):
                    decisions.append(e.get("title", "Action executed"))
        except Exception:
            pass

        return decisions

    def _get_patterns_for_day(self, date: str) -> list[str]:
        """Get patterns detected today."""
        try:
            observations = self._db.get_observations(days=1)
            return [
                f"{o.get('pattern_type', '')}: {o.get('description', '')}"
                for o in observations
                if o.get("timestamp", "").startswith(date)
            ]
        except Exception:
            return []

    def _get_events_for_day(self, date: str) -> list[dict[str, Any]]:
        """Get calendar events for a specific day."""
        since = datetime.fromisoformat(f"{date}T00:00:00")
        results: list[dict[str, Any]] = []

        try:
            events = self._db.get_events(source="calendar", since=since, limit=30)
            for e in events:
                if e.get("timestamp", "").startswith(date):
                    meta = _parse_meta(e)
                    start_time = meta.get("start_time", "")
                    time_display = start_time[11:16] if len(start_time) >= 16 else ""
                    results.append({
                        "title": e.get("title", ""),
                        "time": time_display,
                    })
        except Exception:
            pass

        return results

    def _build_tomorrow_preview(self, events: list[dict[str, Any]]) -> str:
        """Build a one-liner preview of tomorrow."""
        if not events:
            return "No meetings scheduled — deep work day!"
        count = len(events)
        first = events[0].get("title", "Unknown")
        if count == 1:
            return f"1 meeting: {first}"
        return f"{count} meetings, starting with: {first}"

    def _get_observations_summary(self, days: int) -> list[str]:
        """Get observation summary for the period."""
        try:
            observations = self._db.get_observations(days=days)
            return [
                f"[{o.get('pattern_type', '')}] {o.get('description', '')} (confidence: {o.get('confidence', 0):.0%})"
                for o in observations
            ]
        except Exception:
            return []

    def _get_active_projects(self, days: int) -> list[str]:
        """Get projects with recent activity (from context resurrection events)."""
        since = datetime.now() - timedelta(days=days)
        projects: set[str] = set()

        try:
            events = self._db.get_events(event_type="project_activity", since=since, limit=200)
            for e in events:
                source = e.get("source", "")
                if source.startswith("project:"):
                    projects.add(source[8:])
        except Exception:
            pass

        return sorted(projects)

    def _detect_trends(self, daily_stats: list[DayStats]) -> list[str]:
        """Detect trends from daily stats."""
        trends: list[str] = []

        if len(daily_stats) < 2:
            return trends

        # Email volume trend
        email_counts = [d.emails_received for d in daily_stats]
        first_half = email_counts[:len(email_counts) // 2]
        second_half = email_counts[len(email_counts) // 2:]

        avg_first = sum(first_half) / max(len(first_half), 1)
        avg_second = sum(second_half) / max(len(second_half), 1)

        if avg_second > avg_first * 1.3 and avg_first > 0:
            trends.append(f"📈 Email volume increasing ({avg_first:.0f} → {avg_second:.0f}/day)")
        elif avg_second < avg_first * 0.7 and avg_first > 0:
            trends.append(f"📉 Email volume decreasing ({avg_first:.0f} → {avg_second:.0f}/day)")
        elif sum(email_counts) > 0:
            avg = sum(email_counts) / len(email_counts)
            trends.append(f"📊 Email volume stable (~{avg:.0f}/day)")

        # Meeting load
        meeting_counts = [d.calendar_events for d in daily_stats]
        total_meetings = sum(meeting_counts)
        if total_meetings > 0:
            avg_meetings = total_meetings / len(meeting_counts)
            heavy_days = sum(1 for m in meeting_counts if m >= 3)
            if heavy_days >= 3:
                trends.append(f"⚠️ Meeting-heavy week: {heavy_days} days with 3+ meetings")
            elif avg_meetings > 0:
                trends.append(f"📅 Average {avg_meetings:.1f} meetings/day")

        # Action rate (proposals executed / proposals created)
        total_created = sum(d.proposals_created for d in daily_stats)
        total_executed = sum(d.proposals_executed for d in daily_stats)
        if total_created > 0:
            rate = total_executed / total_created
            trends.append(f"✅ Proposal acceptance rate: {rate:.0%} ({total_executed}/{total_created})")

        return trends

    @staticmethod
    def _estimate_time_saved(stats: DayStats) -> int:
        """Estimate minutes saved by automation."""
        return (
            stats.drafts_generated * MINUTES_PER_DRAFT
            + stats.emails_classified * MINUTES_PER_CLASSIFICATION
            + stats.proposals_executed * MINUTES_PER_PROPOSAL
        )


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _parse_meta(event: dict[str, Any]) -> dict[str, Any]:
    """Parse metadata from event dict."""
    meta = event.get("metadata")
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except (ValueError, TypeError):
            return {}
    return meta if isinstance(meta, dict) else {}
