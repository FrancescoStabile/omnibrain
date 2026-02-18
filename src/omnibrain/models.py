"""
OmniBrain — Data Models

All data classes used throughout OmniBrain. These represent the core
domain objects that flow through the system: emails, calendar events,
contacts, proposals, observations, and briefings.

Every field maps 1:1 to the SQLite schema defined in db.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════


class EventSource(str, Enum):
    """Where an event came from."""
    GMAIL = "gmail"
    CALENDAR = "calendar"
    GITHUB = "github"
    FILESYSTEM = "filesystem"
    USER = "user"
    SYSTEM = "system"


class Priority(int, Enum):
    """Priority levels for events, proposals, notifications."""
    UNSET = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class ProposalStatus(str, Enum):
    """Lifecycle of an action proposal."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class NotificationLevel(str, Enum):
    """4-level notification system."""
    SILENT = "silent"       # Stored in memory, no notification
    FYI = "fyi"             # Batched into next briefing
    IMPORTANT = "important" # Immediate notification, non-intrusive
    CRITICAL = "critical"   # Immediate notification, persistent


class Relationship(str, Enum):
    """Contact relationship types."""
    UNKNOWN = "unknown"
    COLLEAGUE = "colleague"
    CLIENT = "client"
    FAMILY = "family"
    FRIEND = "friend"
    INVESTOR = "investor"
    VENDOR = "vendor"


class EmailAction(str, Enum):
    """What to do with an email."""
    RESPOND = "respond"
    FORWARD = "forward"
    ARCHIVE = "archive"
    DELETE = "delete"
    SCHEDULE = "schedule"


class Urgency(str, Enum):
    """Email urgency classification."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BriefingType(str, Enum):
    """Types of briefings."""
    MORNING = "morning"
    EVENING = "evening"
    WEEKLY = "weekly"


# ═══════════════════════════════════════════════════════════════════════════
# Core Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ContactInfo:
    """A person OmniBrain knows about — built from email, calendar, and user input."""

    email: str
    name: str = ""
    relationship: str = Relationship.UNKNOWN.value
    organization: str = ""
    last_interaction: datetime | None = None
    interaction_count: int = 0
    avg_response_time_hours: float = 0.0
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_vip(self) -> bool:
        """High interaction + fast response = VIP."""
        return self.interaction_count >= 10 and self.avg_response_time_hours < 4.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "email": self.email,
            "name": self.name,
            "relationship": self.relationship,
            "organization": self.organization,
            "last_interaction": self.last_interaction.isoformat() if self.last_interaction else None,
            "interaction_count": self.interaction_count,
            "avg_response_time_hours": self.avg_response_time_hours,
            "notes": self.notes,
            "metadata": json.dumps(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContactInfo:
        metadata = data.get("metadata", "{}")
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}
        last_interaction = data.get("last_interaction")
        if isinstance(last_interaction, str) and last_interaction:
            last_interaction = datetime.fromisoformat(last_interaction)
        return cls(
            email=data["email"],
            name=data.get("name", ""),
            relationship=data.get("relationship", Relationship.UNKNOWN.value),
            organization=data.get("organization", ""),
            last_interaction=last_interaction,
            interaction_count=data.get("interaction_count", 0),
            avg_response_time_hours=data.get("avg_response_time_hours", 0.0),
            notes=data.get("notes", ""),
            metadata=metadata,
        )


@dataclass
class CalendarEvent:
    """A calendar event — from Google Calendar or manual input."""

    id: str
    title: str
    start_time: datetime
    end_time: datetime
    attendees: list[str] = field(default_factory=list)
    location: str = ""
    description: str = ""
    is_recurring: bool = False

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)

    @property
    def attendees_summary(self) -> str:
        if not self.attendees:
            return "solo"
        return f"{len(self.attendees)} people"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "attendees": json.dumps(self.attendees),
            "location": self.location,
            "description": self.description,
            "is_recurring": self.is_recurring,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalendarEvent:
        attendees = data.get("attendees", "[]")
        if isinstance(attendees, str):
            attendees = json.loads(attendees) if attendees else []
        return cls(
            id=data["id"],
            title=data["title"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            attendees=attendees,
            location=data.get("location", ""),
            description=data.get("description", ""),
            is_recurring=bool(data.get("is_recurring", False)),
        )


@dataclass
class EmailMessage:
    """An email message — parsed from Gmail API response."""

    id: str
    thread_id: str
    sender: str
    recipients: list[str]
    subject: str
    body: str
    date: datetime
    labels: list[str] = field(default_factory=list)
    is_read: bool = False
    has_attachments: bool = False

    @property
    def sender_email(self) -> str:
        """Extract email from 'Name <email>' format."""
        if "<" in self.sender and ">" in self.sender:
            return self.sender.split("<")[1].rstrip(">")
        return self.sender

    @property
    def sender_name(self) -> str:
        """Extract name from 'Name <email>' format."""
        if "<" in self.sender:
            return self.sender.split("<")[0].strip().strip('"')
        return self.sender

    @property
    def body_preview(self) -> str:
        """First 200 chars of body for classification."""
        return self.body[:200].strip() if self.body else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "sender": self.sender,
            "recipients": json.dumps(self.recipients),
            "subject": self.subject,
            "body": self.body,
            "date": self.date.isoformat(),
            "labels": json.dumps(self.labels),
            "is_read": self.is_read,
            "has_attachments": self.has_attachments,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmailMessage:
        recipients = data.get("recipients", "[]")
        if isinstance(recipients, str):
            recipients = json.loads(recipients) if recipients else []
        labels = data.get("labels", "[]")
        if isinstance(labels, str):
            labels = json.loads(labels) if labels else []
        return cls(
            id=data["id"],
            thread_id=data.get("thread_id", ""),
            sender=data["sender"],
            recipients=recipients,
            subject=data["subject"],
            body=data.get("body", ""),
            date=datetime.fromisoformat(data["date"]),
            labels=labels,
            is_read=bool(data.get("is_read", False)),
            has_attachments=bool(data.get("has_attachments", False)),
        )


@dataclass
class ActionProposal:
    """An action OmniBrain wants to take — pending user approval."""

    id: str
    type: str                   # email_draft, meeting_brief, task, automation, reminder
    title: str
    description: str
    action_data: dict[str, Any] = field(default_factory=dict)
    status: str = ProposalStatus.PENDING.value
    priority: int = Priority.MEDIUM.value
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    result: str = ""

    @property
    def is_pending(self) -> bool:
        return self.status == ProposalStatus.PENDING.value

    @property
    def is_expired(self) -> bool:
        if self.expires_at and self.status == ProposalStatus.PENDING.value:
            return datetime.now() > self.expires_at
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "action_data": json.dumps(self.action_data),
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionProposal:
        action_data = data.get("action_data", "{}")
        if isinstance(action_data, str):
            action_data = json.loads(action_data) if action_data else {}
        expires_at = data.get("expires_at")
        if isinstance(expires_at, str) and expires_at:
            expires_at = datetime.fromisoformat(expires_at)
        return cls(
            id=str(data["id"]),
            type=data["type"],
            title=data["title"],
            description=data.get("description", ""),
            action_data=action_data,
            status=data.get("status", ProposalStatus.PENDING.value),
            priority=data.get("priority", Priority.MEDIUM.value),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            expires_at=expires_at,
            result=data.get("result", ""),
        )


@dataclass
class Observation:
    """A pattern or behavioral observation — feeds the proactive engine."""

    type: str                   # recurring_search, time_pattern, communication_pattern
    detail: str
    evidence: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    frequency: int = 1
    confidence: float = 0.5
    promoted_to_automation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "detail": self.detail,
            "evidence": self.evidence,
            "timestamp": self.timestamp.isoformat(),
            "frequency": self.frequency,
            "confidence": self.confidence,
            "promoted_to_automation": self.promoted_to_automation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif ts is None:
            ts = datetime.now()
        return cls(
            type=data["type"],
            detail=data.get("detail", ""),
            evidence=data.get("evidence", ""),
            timestamp=ts,
            frequency=data.get("frequency", 1),
            confidence=data.get("confidence", 0.5),
            promoted_to_automation=bool(data.get("promoted_to_automation", False)),
        )


@dataclass
class Briefing:
    """A generated briefing report."""

    id: int = 0
    date: str = ""
    type: str = BriefingType.MORNING.value
    content: str = ""
    events_processed: int = 0
    actions_proposed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": self.date,
            "type": self.type,
            "content": self.content,
            "events_processed": self.events_processed,
            "actions_proposed": self.actions_proposed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Briefing:
        return cls(
            id=data.get("id", 0),
            date=data.get("date", ""),
            type=data.get("type", BriefingType.MORNING.value),
            content=data.get("content", ""),
            events_processed=data.get("events_processed", 0),
            actions_proposed=data.get("actions_proposed", 0),
        )


@dataclass
class EmailClassification:
    """LLM-generated classification of an email."""

    email_id: str
    urgency: str = Urgency.MEDIUM.value
    category: str = "fyi"       # action_required, fyi, newsletter, spam, personal
    action: str = EmailAction.ARCHIVE.value
    reasoning: str = ""
    draft_needed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "email_id": self.email_id,
            "urgency": self.urgency,
            "category": self.category,
            "action": self.action,
            "reasoning": self.reasoning,
            "draft_needed": self.draft_needed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmailClassification:
        return cls(
            email_id=data["email_id"],
            urgency=data.get("urgency", Urgency.MEDIUM.value),
            category=data.get("category", "fyi"),
            action=data.get("action", EmailAction.ARCHIVE.value),
            reasoning=data.get("reasoning", ""),
            draft_needed=bool(data.get("draft_needed", False)),
        )
