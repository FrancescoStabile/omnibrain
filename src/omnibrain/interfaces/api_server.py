"""
OmniBrain — REST API Server

FastAPI server that exposes all OmniBrain capabilities via HTTP.
Runs on localhost:7432 by default (internal only).

Endpoints — Core:
    GET  /api/v1/status            — Daemon status + stats
    GET  /api/v1/briefing          — Get latest briefing
    POST /api/v1/briefing/generate — Generate new briefing
    GET  /api/v1/proposals         — List pending proposals
    POST /api/v1/proposals/{id}/approve — Approve proposal
    POST /api/v1/proposals/{id}/reject  — Reject proposal
    POST /api/v1/proposals/{id}/snooze  — Snooze proposal
    GET  /api/v1/search?q=...      — Memory search
    GET  /api/v1/events            — List events
    GET  /api/v1/contacts          — List contacts
    GET  /api/v1/stats             — DB statistics
    POST /api/v1/message           — Process a message

Endpoints — Skills:
    GET    /api/v1/skills              — List installed skills
    POST   /api/v1/skills/{name}/install  — Install a skill
    DELETE /api/v1/skills/{name}       — Remove a skill
    POST   /api/v1/skills/{name}/enable   — Enable a skill
    POST   /api/v1/skills/{name}/disable  — Disable a skill

Endpoints — Settings:
    GET  /api/v1/settings      — Get user settings
    PUT  /api/v1/settings      — Update user settings

Endpoints — Chat:
    POST /api/v1/chat          — Streaming chat (SSE)

Endpoints — OAuth:
    GET  /api/v1/oauth/google          — Initiate Google OAuth
    GET  /api/v1/oauth/google/callback — Handle Google callback
    GET  /api/v1/oauth/status          — Check Google connection
    POST /api/v1/oauth/disconnect      — Disconnect Google

Endpoints — Onboarding:
    POST /api/v1/onboarding/analyze    — Run first-time analysis

Endpoints — Real-time:
    WS   /api/v1/feed          — WebSocket event feed

Auth: Local token stored in ~/.omnibrain/auth_token
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from omnibrain.db import OmniBrainDB
from omnibrain.memory import MemoryManager

logger = logging.getLogger("omnibrain.api")

# Lazy import FastAPI — allows using formatters/helpers without the server
_fastapi_available = False
try:
    from fastapi import Depends, FastAPI, HTTPException, Query, Security, WebSocket, WebSocketDisconnect
    from fastapi.responses import RedirectResponse, StreamingResponse
    from fastapi.security import APIKeyHeader
    from pydantic import BaseModel

    _fastapi_available = True
except ImportError:
    logger.warning("FastAPI not installed — REST API disabled")


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Models (only created if FastAPI is available)
# ═══════════════════════════════════════════════════════════════════════════

if _fastapi_available:

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
        organization: str = ""
        interaction_count: int = 0

    class RejectRequest(BaseModel):
        reason: str = ""

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


# ═══════════════════════════════════════════════════════════════════════════
# API Server
# ═══════════════════════════════════════════════════════════════════════════


class OmniBrainAPIServer:
    """FastAPI-based REST API server for OmniBrain.

    Usage:
        server = OmniBrainAPIServer(db=db, memory_manager=mm)
        app = server.app
        # Then run with uvicorn: uvicorn app:app --host 127.0.0.1 --port 7432

    Or for testing:
        from fastapi.testclient import TestClient
        client = TestClient(server.app)
        response = client.get("/api/v1/status")
    """

    def __init__(
        self,
        db: OmniBrainDB,
        memory_manager: MemoryManager | None = None,
        briefing_gen: Any = None,
        engine_status_fn: Any = None,
        auth_token: str = "",
        version: str = "0.1.0",
        data_dir: Path | None = None,
    ):
        if not _fastapi_available:
            raise RuntimeError("FastAPI not installed")

        self._db = db
        self._memory = memory_manager
        self._briefing_gen = briefing_gen
        self._engine_status_fn = engine_status_fn
        self._auth_token = auth_token
        self._version = version
        self._data_dir = data_dir or Path.home() / ".omnibrain"
        self._start_time = datetime.now()
        self._ws_clients: set[Any] = set()

        self.app = FastAPI(
            title="OmniBrain API",
            version=version,
            description="OmniBrain REST API — your AI chief of staff",
        )

        self._register_routes()

    def _verify_token(self, token: str) -> bool:
        """Verify the API token. Empty auth_token = no auth needed."""
        if not self._auth_token:
            return True
        return secrets.compare_digest(token, self._auth_token)

    def _get_api_origin(self) -> str:
        """Return ``host:port`` for building callback URLs."""
        from omnibrain.config import OmniBrainConfig

        try:
            cfg = OmniBrainConfig()
            return f"{cfg.api_host}:{cfg.api_port}"
        except Exception:
            return "127.0.0.1:7432"

    async def broadcast(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Push an event to all connected WebSocket clients."""
        msg = json.dumps({"type": event_type, **(payload or {})})
        dead: list[Any] = []
        for ws in self._ws_clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    def _register_routes(self) -> None:
        """Register all API routes."""
        app = self.app
        api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

        async def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
            if self._auth_token and (not api_key or not self._verify_token(api_key)):
                raise HTTPException(status_code=401, detail="Invalid or missing API key")
            return api_key or ""

        # ── GET /api/v1/status ──

        @app.get("/api/v1/status", response_model=StatusResponse)
        async def get_status(token: str = Depends(verify_api_key)) -> StatusResponse:
            stats = self._db.get_stats()
            engine = {}
            if self._engine_status_fn:
                try:
                    engine = self._engine_status_fn()
                except Exception:
                    pass

            uptime = (datetime.now() - self._start_time).total_seconds()
            return StatusResponse(
                version=self._version,
                uptime_seconds=round(uptime, 1),
                stats=stats,
                engine=engine,
            )

        # ── GET /api/v1/briefing ──

        @app.get("/api/v1/briefing", response_model=BriefingResponse)
        async def get_briefing(
            type: str = Query("morning", description="Briefing type"),
            token: str = Depends(verify_api_key),
        ) -> BriefingResponse:
            latest = self._db.get_latest_briefing(type)
            if not latest:
                raise HTTPException(status_code=404, detail="No briefing found")
            return BriefingResponse(
                id=latest.get("id", 0),
                date=latest.get("date", ""),
                type=latest.get("type", type),
                content=latest.get("content", ""),
                events_processed=latest.get("events_processed", 0),
                actions_proposed=latest.get("actions_proposed", 0),
            )

        # ── POST /api/v1/briefing/generate ──

        @app.post("/api/v1/briefing/generate", response_model=BriefingResponse)
        async def generate_briefing(
            type: str = Query("morning", description="Briefing type"),
            token: str = Depends(verify_api_key),
        ) -> BriefingResponse:
            if not self._briefing_gen:
                raise HTTPException(status_code=503, detail="Briefing generator not configured")
            try:
                data, text, briefing_id = self._briefing_gen.generate_and_store(type)
                return BriefingResponse(
                    id=briefing_id,
                    date=datetime.now().strftime("%Y-%m-%d"),
                    type=type,
                    content=text,
                    events_processed=data.events_processed,
                    actions_proposed=data.actions_proposed,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        # ── GET /api/v1/briefing/data — Structured briefing ──

        @app.get("/api/v1/briefing/data", response_model=BriefingDataResponse)
        async def get_briefing_data(
            type: str = Query("morning", description="Briefing type"),
            token: str = Depends(verify_api_key),
        ) -> BriefingDataResponse:
            """Return a structured briefing with section-level data.

            Collects fresh data from the database and returns it
            in a card-friendly format for the frontend.
            """
            if not self._briefing_gen:
                # Return empty structured response (still useful for new users)
                user_name = self._db.get_preference("user_name", "")
                h = datetime.now().hour
                period = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
                return BriefingDataResponse(
                    date=datetime.now().strftime("%Y-%m-%d"),
                    briefing_type=type,
                    greeting=f"Good {period}" + (f", {user_name}" if user_name else "") + ".",
                )

            try:
                data = self._briefing_gen.collect_data(type)
                text = self._briefing_gen.format_text(data)

                user_name = self._db.get_preference("user_name", "")
                h = datetime.now().hour
                period = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
                greeting = f"Good {period}" + (f", {user_name}" if user_name else "") + "."

                return BriefingDataResponse(
                    date=data.date,
                    briefing_type=data.briefing_type,
                    greeting=greeting,
                    emails=EmailSectionResponse(**data.emails.to_dict()),
                    calendar=CalendarSectionResponse(
                        total_events=data.calendar.total_events,
                        total_hours=data.calendar.total_hours,
                        next_meeting=data.calendar.next_meeting,
                        next_meeting_time=data.calendar.next_meeting_time,
                        events=[CalendarEventItem(**e) for e in data.calendar.events],
                        conflicts=data.calendar.conflicts,
                    ),
                    proposals=ProposalSectionResponse(**data.proposals.to_dict()),
                    priorities=[
                        PriorityItemResponse(**p.to_dict()) for p in data.priorities
                    ],
                    observations=data.observations,
                    memory_highlights=data.memory_highlights,
                    content=text,
                )
            except Exception as e:
                logger.error("briefing/data error: %s", e)
                raise HTTPException(status_code=500, detail=str(e))

        # ── GET /api/v1/proposals ──

        @app.get("/api/v1/proposals", response_model=list[ProposalResponse])
        async def get_proposals(token: str = Depends(verify_api_key)) -> list[ProposalResponse]:
            proposals = self._db.get_pending_proposals()
            return [
                ProposalResponse(
                    id=p["id"],
                    type=p.get("type", ""),
                    title=p.get("title", ""),
                    description=p.get("description", ""),
                    priority=p.get("priority", 2),
                    status=p.get("status", "pending"),
                    created_at=p.get("created_at", ""),
                )
                for p in proposals
            ]

        # ── POST /api/v1/proposals/{id}/approve ──

        @app.post("/api/v1/proposals/{proposal_id}/approve", response_model=ProposalActionResponse)
        async def approve_proposal(proposal_id: int, token: str = Depends(verify_api_key)) -> ProposalActionResponse:
            ok = self._db.update_proposal_status(proposal_id, "approved")
            if not ok:
                raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
            return ProposalActionResponse(ok=True, proposal_id=proposal_id, new_status="approved")

        # ── POST /api/v1/proposals/{id}/reject ──

        @app.post("/api/v1/proposals/{proposal_id}/reject", response_model=ProposalActionResponse)
        async def reject_proposal(
            proposal_id: int,
            body: RejectRequest | None = None,
            token: str = Depends(verify_api_key),
        ) -> ProposalActionResponse:
            reason = body.reason if body else ""
            ok = self._db.update_proposal_status(proposal_id, "rejected", result=reason)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
            return ProposalActionResponse(ok=True, proposal_id=proposal_id, new_status="rejected")

        # ── GET /api/v1/search ──

        @app.get("/api/v1/search", response_model=SearchResponse)
        async def search(
            q: str = Query(..., description="Search query"),
            limit: int = Query(10, ge=1, le=50, description="Max results"),
            source: str = Query("all", description="Source filter"),
            token: str = Depends(verify_api_key),
        ) -> SearchResponse:
            if not self._memory:
                raise HTTPException(status_code=503, detail="Memory search not available")

            results = self._memory.search(q, max_results=limit, source_filter=source)
            return SearchResponse(
                query=q,
                results=[
                    SearchResult(
                        id=doc.id,
                        text=doc.text[:500],
                        source=doc.source,
                        source_type=doc.source_type,
                        score=doc.score or 0.0,
                    )
                    for doc in results
                ],
                count=len(results),
            )

        # ── GET /api/v1/events ──

        @app.get("/api/v1/events", response_model=list[EventResponse])
        async def get_events(
            source: str = Query("", description="Filter by source"),
            limit: int = Query(50, ge=1, le=200, description="Max events"),
            token: str = Depends(verify_api_key),
        ) -> list[EventResponse]:
            kwargs: dict[str, Any] = {"limit": limit}
            if source:
                kwargs["source"] = source
            events = self._db.get_events(**kwargs)
            return [
                EventResponse(
                    id=e.get("id", 0),
                    source=e.get("source", ""),
                    title=e.get("title", ""),
                    priority=e.get("priority", 0),
                    timestamp=e.get("timestamp", ""),
                    processed=bool(e.get("processed", False)),
                )
                for e in events
            ]

        # ── GET /api/v1/contacts ──

        @app.get("/api/v1/contacts", response_model=list[ContactResponse])
        async def get_contacts(
            limit: int = Query(100, ge=1, le=500, description="Max contacts"),
            token: str = Depends(verify_api_key),
        ) -> list[ContactResponse]:
            contacts = self._db.get_contacts(limit=limit)
            return [
                ContactResponse(
                    email=c.email,
                    name=c.name,
                    relationship=c.relationship,
                    organization=c.organization,
                    interaction_count=c.interaction_count,
                )
                for c in contacts
            ]

        # ── GET /api/v1/stats ──

        @app.get("/api/v1/stats")
        async def get_stats(token: str = Depends(verify_api_key)) -> dict[str, int]:
            return self._db.get_stats()

        # ── POST /api/v1/message ──

        @app.post("/api/v1/message", response_model=MessageResponse)
        async def process_message(
            body: MessageRequest,
            token: str = Depends(verify_api_key),
        ) -> MessageResponse:
            """Process a user message. Phase 1: memory search. Phase 2: full agent."""
            if not body.text.strip():
                raise HTTPException(status_code=400, detail="Empty message")

            if self._memory:
                results = self._memory.search(body.text, max_results=3)
                if results:
                    combined = "\n".join(doc.text[:200] for doc in results)
                    return MessageResponse(response=combined, source="memory")

            return MessageResponse(
                response="No relevant information found. Full agent processing coming in Phase 2.",
                source="none",
            )

        # ── POST /api/v1/proposals/{id}/snooze ──

        @app.post("/api/v1/proposals/{proposal_id}/snooze", response_model=ProposalActionResponse)
        async def snooze_proposal(
            proposal_id: int, token: str = Depends(verify_api_key),
        ) -> ProposalActionResponse:
            ok = self._db.update_proposal_status(proposal_id, "snoozed")
            if not ok:
                raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
            return ProposalActionResponse(ok=True, proposal_id=proposal_id, new_status="snoozed")

        # ══════════════════════════════════════════════════════════════════
        # Skills endpoints
        # ══════════════════════════════════════════════════════════════════

        @app.get("/api/v1/skills", response_model=SkillsListResponse)
        async def get_skills(token: str = Depends(verify_api_key)) -> SkillsListResponse:
            rows = self._db.get_installed_skills()
            skills = []
            for r in rows:
                perms = r.get("permissions", "[]")
                if isinstance(perms, str):
                    perms = json.loads(perms) if perms else []
                skills.append(SkillResponse(
                    name=r["name"],
                    version=r.get("version", ""),
                    description=r.get("description", ""),
                    author=r.get("author", ""),
                    category=r.get("category", "other"),
                    icon=r.get("icon", ""),
                    permissions=perms,
                    enabled=bool(r.get("enabled", 1)),
                    installed=True,
                ))
            return SkillsListResponse(skills=skills)

        @app.post("/api/v1/skills/{skill_name}/install", response_model=SkillActionResponse)
        async def install_skill(
            skill_name: str,
            body: InstallSkillRequest | None = None,
            token: str = Depends(verify_api_key),
        ) -> SkillActionResponse:
            b = body or InstallSkillRequest()
            self._db.install_skill(
                name=skill_name,
                version=b.version,
                description=b.description,
                author=b.author,
                category=b.category,
                permissions=b.permissions,
            )
            return SkillActionResponse(status="installed")

        @app.delete("/api/v1/skills/{skill_name}", response_model=SkillActionResponse)
        async def remove_skill(
            skill_name: str, token: str = Depends(verify_api_key),
        ) -> SkillActionResponse:
            ok = self._db.remove_skill(skill_name)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
            return SkillActionResponse(status="removed")

        @app.post("/api/v1/skills/{skill_name}/enable", response_model=SkillActionResponse)
        async def enable_skill(
            skill_name: str, token: str = Depends(verify_api_key),
        ) -> SkillActionResponse:
            ok = self._db.set_skill_enabled(skill_name, True)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
            return SkillActionResponse(status="enabled")

        @app.post("/api/v1/skills/{skill_name}/disable", response_model=SkillActionResponse)
        async def disable_skill(
            skill_name: str, token: str = Depends(verify_api_key),
        ) -> SkillActionResponse:
            ok = self._db.set_skill_enabled(skill_name, False)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
            return SkillActionResponse(status="disabled")

        # ══════════════════════════════════════════════════════════════════
        # Settings endpoints
        # ══════════════════════════════════════════════════════════════════

        @app.get("/api/v1/settings", response_model=SettingsResponse)
        async def get_settings(token: str = Depends(verify_api_key)) -> SettingsResponse:
            prefs = self._db.get_all_preferences()
            return SettingsResponse(
                profile={
                    "name": prefs.get("user_name", ""),
                    "timezone": prefs.get("timezone", "UTC"),
                    "language": prefs.get("language", "en"),
                },
                notifications={
                    "silent": prefs.get("notify_silent", True),
                    "fyi": prefs.get("notify_fyi", True),
                    "important": prefs.get("notify_important", True),
                    "critical": prefs.get("notify_critical", True),
                },
                llm={
                    "primary_provider": prefs.get("llm_primary", "deepseek"),
                    "fallback_provider": prefs.get("llm_fallback", "openai"),
                    "monthly_budget": prefs.get("llm_budget", 10.0),
                    "current_month_cost": prefs.get("llm_month_cost", 0.0),
                },
                appearance={
                    "theme": prefs.get("theme", "dark"),
                },
            )

        @app.put("/api/v1/settings", response_model=SettingsResponse)
        async def update_settings(
            body: SettingsResponse, token: str = Depends(verify_api_key),
        ) -> SettingsResponse:
            if body.profile:
                for k, v in body.profile.items():
                    key = "user_name" if k == "name" else k
                    self._db.set_preference(key, v, learned_from="api")
            if body.notifications:
                for k, v in body.notifications.items():
                    self._db.set_preference(f"notify_{k}", v, learned_from="api")
            if body.llm:
                mapping = {
                    "primary_provider": "llm_primary",
                    "fallback_provider": "llm_fallback",
                    "monthly_budget": "llm_budget",
                }
                for k, v in body.llm.items():
                    pref_key = mapping.get(k, k)
                    self._db.set_preference(pref_key, v, learned_from="api")
            if body.appearance:
                for k, v in body.appearance.items():
                    self._db.set_preference(k, v, learned_from="api")
            # Return the fresh state
            return await get_settings(token=token)

        # ══════════════════════════════════════════════════════════════════
        # Chat streaming (SSE)
        # ══════════════════════════════════════════════════════════════════

        @app.post("/api/v1/chat")
        async def chat_stream(
            body: ChatRequest, token: str = Depends(verify_api_key),
        ) -> StreamingResponse:
            """Streaming chat via Server-Sent Events.

            Falls back to memory search until the full agent is wired.
            """
            async def event_generator() -> Any:
                # Phase 1: memory-backed response
                response_text = ""
                if self._memory and body.message.strip():
                    results = self._memory.search(body.message, max_results=3)
                    if results:
                        response_text = "\n".join(doc.text[:200] for doc in results)

                if not response_text:
                    response_text = (
                        "I'm still learning. Full conversational AI will be "
                        "available once the agent pipeline is connected."
                    )

                # Stream the response token-by-token (simulated for now)
                words = response_text.split()
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    data = json.dumps({"type": "token", "content": chunk})
                    yield f"data: {data}\n\n"
                    await asyncio.sleep(0.02)

                # End signal
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # ══════════════════════════════════════════════════════════════════
        # OAuth — Google
        # ══════════════════════════════════════════════════════════════════

        @app.get("/api/v1/oauth/google", response_model=OAuthUrlResponse)
        async def oauth_google_start(
            scope: str = Query("gmail+calendar", description="Scope groups"),
            redirect: str = Query("", description="Frontend redirect after auth"),
            token: str = Depends(verify_api_key),
        ) -> OAuthUrlResponse:
            """Generate Google OAuth consent URL."""
            from omnibrain.auth.google_oauth import GoogleOAuthManager

            mgr = GoogleOAuthManager(self._data_dir)
            if not mgr.has_client_credentials():
                raise HTTPException(
                    status_code=503,
                    detail="Google OAuth not configured — google_credentials.json missing",
                )

            callback_url = f"http://{self._get_api_origin()}/api/v1/oauth/google/callback"
            state = redirect or ""
            auth_url = mgr.create_auth_url(
                redirect_uri=callback_url,
                scopes=scope,
                state=state,
            )
            return OAuthUrlResponse(auth_url=auth_url)

        @app.get("/api/v1/oauth/google/callback")
        async def oauth_google_callback(
            code: str = Query(..., description="Auth code from Google"),
            state: str = Query("", description="Original redirect URL"),
        ) -> RedirectResponse:
            """Handle Google OAuth callback — exchange code, save tokens."""
            from omnibrain.auth.google_oauth import GoogleOAuthError, GoogleOAuthManager

            mgr = GoogleOAuthManager(self._data_dir)
            callback_url = f"http://{self._get_api_origin()}/api/v1/oauth/google/callback"

            try:
                tokens = mgr.exchange_code(code, callback_url)
                mgr.save_tokens(tokens)
            except GoogleOAuthError as e:
                logger.error("OAuth callback failed: %s", e)
                err_base = state or ""
                if err_base and not err_base.startswith("http"):
                    err_base = ""
                if err_base:
                    err_sep = "&" if "?" in err_base else "?"
                    err_url = f"{err_base}{err_sep}oauth=error&message={str(e)}"
                else:
                    err_url = f"/?oauth=error&message={str(e)}"
                return RedirectResponse(url=err_url)

            # Broadcast to WS clients
            await self.broadcast("google_connected", {"email": mgr.get_user_info().get("email", "")})

            # state carries the frontend origin (e.g. http://localhost:3000)
            base = state or ""
            if base and not base.startswith("http"):
                base = ""
            if base:
                sep = "&" if "?" in base else "?"
                redirect_url = f"{base}{sep}oauth=success"
            else:
                redirect_url = "/?oauth=success"
            return RedirectResponse(url=redirect_url)

        @app.get("/api/v1/oauth/status", response_model=OAuthStatusResponse)
        async def oauth_status(
            token: str = Depends(verify_api_key),
        ) -> OAuthStatusResponse:
            """Check whether Google is connected."""
            from omnibrain.auth.google_oauth import GoogleOAuthManager

            mgr = GoogleOAuthManager(self._data_dir)
            if not mgr.is_connected():
                return OAuthStatusResponse(
                    connected=False,
                    has_client_credentials=mgr.has_client_credentials(),
                )
            info = mgr.get_user_info()
            return OAuthStatusResponse(
                connected=True,
                email=info.get("email", ""),
                name=info.get("name", ""),
                scopes=["gmail.readonly", "calendar.readonly"],
                has_client_credentials=True,
            )

        @app.post("/api/v1/oauth/disconnect", response_model=OAuthDisconnectResponse)
        async def oauth_disconnect(
            token: str = Depends(verify_api_key),
        ) -> OAuthDisconnectResponse:
            """Disconnect Google (remove stored token)."""
            from omnibrain.auth.google_oauth import GoogleOAuthManager

            mgr = GoogleOAuthManager(self._data_dir)
            removed = mgr.disconnect()
            if removed:
                await self.broadcast("google_disconnected")
            return OAuthDisconnectResponse(disconnected=removed)

        # ══════════════════════════════════════════════════════════════════
        # Onboarding — first-time analysis
        # ══════════════════════════════════════════════════════════════════

        @app.post("/api/v1/onboarding/analyze", response_model=OnboardingResultResponse)
        async def onboarding_analyze(
            token: str = Depends(verify_api_key),
        ) -> OnboardingResultResponse:
            """Run first-time analysis (Holy Shit moment).

            Fetches 7 days of emails + upcoming events, counts contacts,
            and generates insight cards. Runs in a thread pool to avoid
            blocking the event loop.
            """
            from omnibrain.auth.google_oauth import GoogleOAuthManager
            from omnibrain.auth.onboarding import OnboardingAnalyzer

            mgr = GoogleOAuthManager(self._data_dir)
            if not mgr.is_connected():
                raise HTTPException(
                    status_code=400,
                    detail="Google not connected — complete OAuth first",
                )

            analyzer = OnboardingAnalyzer(self._data_dir)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, analyzer.analyze)

            # Store onboarding completion in preferences
            try:
                self._db.set_preference("onboarding_complete", True, learned_from="onboarding")
                if result.user_name:
                    self._db.set_preference("user_name", result.user_name, learned_from="onboarding")
                if result.user_email:
                    self._db.set_preference("user_email", result.user_email, learned_from="onboarding")
            except Exception as e:
                logger.warning("Failed to store onboarding prefs: %s", e)

            return OnboardingResultResponse(
                greeting=result.greeting,
                stats=result.stats,
                insights=[
                    InsightCardResponse(
                        icon=c.icon,
                        title=c.title,
                        body=c.body,
                        action=c.action,
                        action_type=c.action_type,
                        priority=c.priority,
                    )
                    for c in result.insights
                ],
                user_email=result.user_email,
                user_name=result.user_name,
                completed_at=result.completed_at,
                duration_ms=result.duration_ms,
            )

        # ══════════════════════════════════════════════════════════════════
        # WebSocket feed for real-time events
        # ══════════════════════════════════════════════════════════════════

        @app.websocket("/api/v1/feed")
        async def websocket_feed(ws: WebSocket) -> None:
            """Real-time event feed.

            Pushes new proposals, skill events, and status updates to
            connected Web UI clients.
            """
            await ws.accept()
            self._ws_clients.add(ws)
            try:
                while True:
                    # Keep-alive: wait for client messages (pings)
                    data = await ws.receive_text()
                    if data == "ping":
                        await ws.send_json({"type": "pong"})
            except WebSocketDisconnect:
                pass
            finally:
                self._ws_clients.discard(ws)


def create_api_server(
    data_dir: Path | None = None,
    auth_token: str = "",
    version: str = "0.1.0",
) -> OmniBrainAPIServer:
    """Factory function to create an API server with default wiring.

    Used by the CLI `omnibrain api` command and the daemon.
    """
    from omnibrain.config import OmniBrainConfig

    config = OmniBrainConfig()
    actual_dir = data_dir or config.data_dir
    db = OmniBrainDB(actual_dir)

    memory = None
    try:
        memory = MemoryManager(actual_dir, enable_chroma=False)
    except Exception:
        pass

    briefing_gen = None
    if memory:
        from omnibrain.briefing import BriefingGenerator
        briefing_gen = BriefingGenerator(db, memory)

    return OmniBrainAPIServer(
        db=db,
        memory_manager=memory,
        briefing_gen=briefing_gen,
        auth_token=auth_token,
        version=version,
        data_dir=actual_dir,
    )
