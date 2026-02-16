"""
OmniBrain — Profile (DomainProfile Subclass)

Everything OmniBrain knows about the user. Auto-populated from tool results
(Gmail, Calendar, memory, patterns) and injected into LLM context.

This is the central knowledge store — updated by extractors after every tool call.

Follows manifesto Section 7:
    OmnibrainProfile(DomainProfile) with typed fields for personal AI context.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from omnigent.domain_profile import DomainProfile, Hypothesis

from omnibrain.models import (
    ActionProposal,
    CalendarEvent,
    ContactInfo,
    Observation,
)


# ═══════════════════════════════════════════════════════════════════════════
# EmailStats — communication summary
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class EmailStats:
    """Summary statistics about the user's email."""

    total_today: int = 0
    unread_total: int = 0
    unread_urgent: int = 0
    urgent_list: list[dict[str, Any]] = field(default_factory=list)
    top_senders: list[str] = field(default_factory=list)
    categories: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmailStats:
        if not data:
            return cls()
        return cls(
            total_today=data.get("total_today", 0),
            unread_total=data.get("unread_total", 0),
            unread_urgent=data.get("unread_urgent", 0),
            urgent_list=data.get("urgent_list", []),
            top_senders=data.get("top_senders", []),
            categories=data.get("categories", {}),
        )


# ═══════════════════════════════════════════════════════════════════════════
# ProjectContext — for developer users
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ProjectContext:
    """Context about an active project — for developer users."""

    name: str = ""
    path: str = ""
    language: str = ""
    recent_commits: list[str] = field(default_factory=list)
    open_issues: int = 0
    last_activity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectContext:
        if not data:
            return cls()
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            language=data.get("language", ""),
            recent_commits=data.get("recent_commits", []),
            open_issues=data.get("open_issues", 0),
            last_activity=data.get("last_activity", ""),
        )


# ═══════════════════════════════════════════════════════════════════════════
# OmniBrainProfile
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class OmniBrainProfile(DomainProfile):
    """Everything OmniBrain knows about the user.

    Extends Omnigent's DomainProfile with personal AI context:
    - Identity and preferences
    - Contact knowledge base
    - Communication patterns
    - Calendar context
    - Project context (for developers)
    - Action proposals and observations

    Updated by extractors after each tool call.
    Serialized with sessions for persistence.
    Injected into LLM context via to_prompt_summary().
    """

    # ── Identity ──
    user_name: str = ""
    user_email: str = ""
    timezone: str = "Europe/Rome"

    # ── Contacts (extracted from emails, calendar) ──
    contacts: dict[str, ContactInfo] = field(default_factory=dict)
    # key = email address, value = ContactInfo

    # ── Communication patterns ──
    email_stats: EmailStats = field(default_factory=EmailStats)
    response_patterns: dict[str, float] = field(default_factory=dict)
    # key = contact email, value = avg response time in hours

    # ── Calendar context ──
    today_events: list[CalendarEvent] = field(default_factory=list)
    upcoming_events: list[CalendarEvent] = field(default_factory=list)

    # ── Project context (for developers) ──
    active_projects: list[ProjectContext] = field(default_factory=list)

    # ── Action proposals (pending user approval) ──
    pending_proposals: list[ActionProposal] = field(default_factory=list)

    # ── Observations (for pattern detection) ──
    observations: list[Observation] = field(default_factory=list)

    # ── User preferences (learned over time) ──
    preferences: dict[str, Any] = field(default_factory=dict)

    # ── Context injection ──

    def to_prompt_summary(self) -> str:
        """Generate context for LLM — what OmniBrain knows right now.

        This is injected into every LLM call so the agent has full context
        about the user's current state.
        """
        lines = [f"## User Context: {self.user_name or 'Unknown'}"]
        lines.append(f"Timezone: {self.timezone}")
        lines.append(f"Current time: {datetime.now().strftime('%H:%M %A %B %d')}")

        # Today's schedule
        if self.today_events:
            lines.append(f"\n### Today's Schedule ({len(self.today_events)} events)")
            for e in self.today_events[:8]:
                time_str = e.start_time.strftime("%H:%M") if hasattr(e.start_time, "strftime") else str(e.start_time)
                attendees = e.attendees_summary if hasattr(e, "attendees_summary") else ""
                lines.append(f"- {time_str} — {e.title} ({attendees})")

        # Upcoming events
        if self.upcoming_events:
            lines.append(f"\n### Upcoming Events ({len(self.upcoming_events)} in next days)")
            for e in self.upcoming_events[:5]:
                date_str = e.start_time.strftime("%a %d %b %H:%M") if hasattr(e.start_time, "strftime") else str(e.start_time)
                lines.append(f"- {date_str} — {e.title}")

        # Urgent emails
        if self.email_stats.unread_urgent:
            lines.append(f"\n### Urgent Emails ({self.email_stats.unread_urgent})")
            for e in self.email_stats.urgent_list[:5]:
                sender = e.get("sender", "?")
                subject = e.get("subject", "?")
                lines.append(f"- From: {sender} — {subject}")

        # Email stats
        if self.email_stats.total_today > 0:
            lines.append(f"\n### Email Summary")
            lines.append(f"- Today: {self.email_stats.total_today} emails ({self.email_stats.unread_total} unread)")

        # Pending actions
        if self.pending_proposals:
            pending = [p for p in self.pending_proposals if p.is_pending]
            if pending:
                lines.append(f"\n### Pending Actions ({len(pending)})")
                for p in pending[:5]:
                    lines.append(f"- [{p.type}] {p.title}")

        # Active projects
        if self.active_projects:
            lines.append(f"\n### Active Projects ({len(self.active_projects)})")
            for proj in self.active_projects[:5]:
                lines.append(f"- {proj.name}: {proj.language}, {proj.open_issues} issues")

        # Confirmed insights from parent DomainProfile
        confirmed = self.get_confirmed()
        if confirmed:
            lines.append(f"\n### Confirmed Insights ({len(confirmed)})")
            for h in confirmed[:5]:
                lines.append(f"- {h}")

        # Key contacts
        vip_contacts = [c for c in self.contacts.values() if c.is_vip]
        if vip_contacts:
            lines.append(f"\n### Key Contacts ({len(vip_contacts)} VIPs)")
            for c in vip_contacts[:5]:
                lines.append(f"- {c.name or c.email} ({c.relationship})")

        return "\n".join(lines)

    # ── Mutation helpers ──

    def update_contacts_from_emails(self, contacts: list[ContactInfo]) -> int:
        """Update contact knowledge base from extracted email contacts.

        Returns number of new/updated contacts.
        """
        updated = 0
        for contact in contacts:
            existing = self.contacts.get(contact.email)
            if existing:
                # Update interaction count
                existing.interaction_count += 1
                if contact.last_interaction:
                    existing.last_interaction = contact.last_interaction
                if contact.name and not existing.name:
                    existing.name = contact.name
            else:
                self.contacts[contact.email] = contact
            updated += 1
        self._touch()
        return updated

    def update_today_events(self, events: list[CalendarEvent]) -> None:
        """Replace today's events with fresh data."""
        self.today_events = events
        self._touch()

    def update_upcoming_events(self, events: list[CalendarEvent]) -> None:
        """Replace upcoming events with fresh data."""
        self.upcoming_events = events
        self._touch()

    def add_observation(self, observation: Observation) -> None:
        """Add a behavioral observation."""
        self.observations.append(observation)
        self._touch()

    def add_proposal(self, proposal: ActionProposal) -> None:
        """Add a pending action proposal."""
        self.pending_proposals.append(proposal)
        self._touch()

    def set_preference(self, key: str, value: Any) -> None:
        """Set a learned preference."""
        self.preferences[key] = value
        self._touch()

    # ── Serialization ──

    def to_dict(self) -> dict[str, Any]:
        """Serialize for session persistence."""
        base = super().to_dict()
        base.update({
            "user_name": self.user_name,
            "user_email": self.user_email,
            "timezone": self.timezone,
            "contacts": {k: v.to_dict() for k, v in self.contacts.items()},
            "email_stats": self.email_stats.to_dict(),
            "response_patterns": self.response_patterns,
            "today_events": [e.to_dict() for e in self.today_events],
            "upcoming_events": [e.to_dict() for e in self.upcoming_events],
            "active_projects": [p.to_dict() for p in self.active_projects],
            "pending_proposals": [p.to_dict() for p in self.pending_proposals],
            "observations": [o.to_dict() for o in self.observations],
            "preferences": self.preferences,
        })
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OmniBrainProfile:
        """Deserialize from session data."""
        if not data:
            return cls()

        profile = cls()

        # DomainProfile base fields
        profile.subject = data.get("subject", "")
        profile.scope = data.get("scope", [])
        profile.metadata = data.get("metadata", {})
        profile.last_updated = data.get("last_updated", datetime.now().isoformat())
        for h in data.get("hypotheses", []):
            if isinstance(h, dict):
                profile.hypotheses.append(Hypothesis(**h))

        # OmniBrain-specific fields
        profile.user_name = data.get("user_name", "")
        profile.user_email = data.get("user_email", "")
        profile.timezone = data.get("timezone", "Europe/Rome")
        profile.preferences = data.get("preferences", {})
        profile.response_patterns = data.get("response_patterns", {})

        # Contacts
        contacts_data = data.get("contacts", {})
        for email, cdata in contacts_data.items():
            if isinstance(cdata, dict):
                profile.contacts[email] = ContactInfo.from_dict(cdata)

        # Email stats
        profile.email_stats = EmailStats.from_dict(data.get("email_stats", {}))

        # Calendar events
        for edata in data.get("today_events", []):
            if isinstance(edata, dict):
                profile.today_events.append(CalendarEvent.from_dict(edata))
        for edata in data.get("upcoming_events", []):
            if isinstance(edata, dict):
                profile.upcoming_events.append(CalendarEvent.from_dict(edata))

        # Projects
        for pdata in data.get("active_projects", []):
            if isinstance(pdata, dict):
                profile.active_projects.append(ProjectContext.from_dict(pdata))

        # Proposals
        for pdata in data.get("pending_proposals", []):
            if isinstance(pdata, dict):
                profile.pending_proposals.append(ActionProposal.from_dict(pdata))

        # Observations
        for odata in data.get("observations", []):
            if isinstance(odata, dict):
                profile.observations.append(Observation(**odata))

        return profile
