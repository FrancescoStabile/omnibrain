"""Pydantic models for the OmniBrain REST API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# ═══════════════════════════════════════════════════════════════════════════
# Core models
# ═══════════════════════════════════════════════════════════════════════════


class StatusResponse(BaseModel):
    version: str
    uptime_seconds: float = 0.0
    stats: dict[str, int] = {}
    engine: dict[str, Any] = {}


class BriefingResponse(BaseModel):
    id: int = 0
    date: str = ""
    type: str = "morning"
    content: str = ""
    events_processed: int = 0
    actions_proposed: int = 0


class ProposalResponse(BaseModel):
    id: int
    type: str = ""
    title: str = ""
    description: str = ""
    priority: int = 2
    status: str = "pending"
    created_at: str = ""


class ProposalActionResponse(BaseModel):
    ok: bool
    proposal_id: int
    new_status: str


class SearchResult(BaseModel):
    id: str = ""
    text: str = ""
    source: str = ""
    source_type: str = ""
    score: float = 0.0


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    count: int


class MessageRequest(BaseModel):
    text: str
    context: dict[str, Any] = {}


class MessageResponse(BaseModel):
    response: str
    source: str = "memory"


class EventResponse(BaseModel):
    id: int = 0
    source: str = ""
    title: str = ""
    priority: int = 0
    timestamp: str = ""
    processed: bool = False


class ContactResponse(BaseModel):
    email: str
    name: str = ""
    relationship: str = ""
    organization: str | None = ""
    interaction_count: int = 0


class RejectRequest(BaseModel):
    reason: str = ""


class SnoozeRequest(BaseModel):
    hours: int = 4


class SkillResponse(BaseModel):
    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    category: str = "other"
    icon: str = ""
    permissions: list[str] = []
    enabled: bool = True
    installed: bool = True


class SkillsListResponse(BaseModel):
    skills: list[SkillResponse]


class SkillActionResponse(BaseModel):
    status: str = "ok"


class InstallSkillRequest(BaseModel):
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    category: str = "other"
    permissions: list[str] = []


class SettingsResponse(BaseModel):
    profile: dict[str, Any] = {}
    notifications: dict[str, Any] = {}
    llm: dict[str, Any] = {}
    appearance: dict[str, Any] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    stream: bool = False


# ── OAuth + Onboarding models ──


class OAuthUrlResponse(BaseModel):
    auth_url: str


class OAuthStatusResponse(BaseModel):
    connected: bool = False
    email: str = ""
    name: str = ""
    scopes: list[str] = []
    has_client_credentials: bool = False


class OAuthDisconnectResponse(BaseModel):
    disconnected: bool = False


class InsightCardResponse(BaseModel):
    icon: str = ""
    title: str = ""
    body: str = ""
    action: str = ""
    action_type: str = ""
    priority: int = 0


class OnboardingResultResponse(BaseModel):
    greeting: str = ""
    stats: dict[str, int] = {}
    insights: list[InsightCardResponse] = []
    user_email: str = ""
    user_name: str = ""
    completed_at: str = ""
    duration_ms: int = 0


class OnboardingProfileRequest(BaseModel):
    """Profile info gathered from conversational onboarding."""
    name: str = ""
    work: str = ""
    goals: str = ""
    timezone: str = ""


# ── Structured Briefing models ──


class EmailSectionResponse(BaseModel):
    total: int = 0
    unread: int = 0
    urgent: int = 0
    needs_response: int = 0
    drafts_ready: int = 0
    top_senders: list[str] = []


class CalendarEventItem(BaseModel):
    title: str = ""
    time: str = ""
    attendees: int = 0
    duration: int = 0


class CalendarSectionResponse(BaseModel):
    total_events: int = 0
    total_hours: float = 0.0
    next_meeting: str = ""
    next_meeting_time: str = ""
    events: list[CalendarEventItem] = []
    conflicts: list[str] = []


class ProposalSectionResponse(BaseModel):
    total_pending: int = 0
    by_type: dict[str, int] = {}
    high_priority: list[dict[str, Any]] = []


class PriorityItemResponse(BaseModel):
    rank: int = 0
    title: str = ""
    reason: str = ""
    source: str = ""


class BriefingDataResponse(BaseModel):
    """Structured briefing for the frontend card-based view."""
    date: str = ""
    briefing_type: str = "morning"
    greeting: str = ""
    emails: EmailSectionResponse = EmailSectionResponse()
    calendar: CalendarSectionResponse = CalendarSectionResponse()
    proposals: ProposalSectionResponse = ProposalSectionResponse()
    priorities: list[PriorityItemResponse] = []
    observations: list[str] = []
    memory_highlights: list[str] = []
    content: str = ""  # Formatted text fallback
