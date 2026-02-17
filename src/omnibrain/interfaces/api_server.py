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
from omnibrain.skill_context import EventBus
from omnibrain.skill_runtime import SkillRuntime

from omnigent.router import LLMRouter, Provider, StreamChunk

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
        router: LLMRouter | None = None,
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
        self._router = router

        # Load system prompt
        self._system_prompt = self._load_system_prompt()

        self.app = FastAPI(
            title="OmniBrain API",
            version=version,
            description="OmniBrain REST API — your AI chief of staff",
        )

        self._register_routes()

    def _load_system_prompt(self) -> str:
        """Load the system prompt from prompts/system.md."""
        prompt_file = Path(__file__).parent.parent / "prompts" / "system.md"
        if prompt_file.exists():
            return prompt_file.read_text()
        return "You are OmniBrain, a personal AI assistant."

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

                # Auto-store if no briefing for today yet
                today = datetime.now().strftime("%Y-%m-%d")
                try:
                    latest = self._db.get_latest_briefing(type)
                    if not latest or latest.get("date") != today:
                        self._briefing_gen.store(data, text)
                        logger.info("Auto-stored %s briefing for %s", type, today)
                except Exception:
                    pass

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
            """Process a user message. Uses LLM with memory context."""
            if not body.text.strip():
                raise HTTPException(status_code=400, detail="Empty message")

            # Search memory for context
            memory_context = ""
            if self._memory:
                results = self._memory.search(body.text, max_results=3)
                if results:
                    memory_context = "\n".join(doc.text[:200] for doc in results)

            # Call LLM if router is available
            if self._router:
                try:
                    system = self._system_prompt
                    if memory_context:
                        system += f"\n\nRelevant memories:\n{memory_context}"

                    messages = [{"role": "user", "content": body.text}]
                    response_parts: list[str] = []
                    async for chunk in self._router.stream(messages=messages, system=system):
                        if chunk.content:
                            response_parts.append(chunk.content)
                        if chunk.done:
                            break
                    response = "".join(response_parts)

                    # Store in memory
                    if self._memory and response.strip():
                        self._memory.store(
                            text=f"User: {body.text}\nAssistant: {response[:500]}",
                            source="chat",
                            source_type="conversation",
                        )

                    return MessageResponse(response=response, source="llm")
                except Exception as e:
                    logger.error(f"LLM call failed in /message: {e}")

            # Fallback to memory
            if memory_context:
                return MessageResponse(response=memory_context, source="memory")

            return MessageResponse(
                response="I'm OmniBrain. No LLM API key is configured yet — check your .env file.",
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

        @app.get("/api/v1/skills/runtime")
        async def get_skills_runtime(token: str = Depends(verify_api_key)) -> dict[str, Any]:
            """Return live SkillRuntime status (loaded skills, triggers, running state)."""
            runtime = getattr(self, "_skill_runtime", None)
            if not runtime:
                return {"running": False, "skill_count": 0, "skills": {}}
            return runtime.get_status()

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
            # Also activate in SkillRuntime if skill directory exists
            runtime = getattr(self, "_skill_runtime", None)
            if runtime and not runtime.has_skill(skill_name):
                project_root = Path(__file__).resolve().parent.parent.parent
                data_dir = getattr(self, "_data_dir", Path.home() / ".omnibrain")
                for skill_dir in [project_root / "skills", data_dir / "skills"]:
                    candidate = skill_dir / skill_name
                    if (candidate / "skill.yaml").is_file():
                        runtime.discover([skill_dir])
                        break
            return SkillActionResponse(status="installed")

        @app.delete("/api/v1/skills/{skill_name}", response_model=SkillActionResponse)
        async def remove_skill(
            skill_name: str, token: str = Depends(verify_api_key),
        ) -> SkillActionResponse:
            ok = self._db.remove_skill(skill_name)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
            # Disable in runtime so it stops triggering
            runtime = getattr(self, "_skill_runtime", None)
            if runtime:
                runtime.set_skill_enabled(skill_name, False)
            return SkillActionResponse(status="removed")

        @app.post("/api/v1/skills/{skill_name}/enable", response_model=SkillActionResponse)
        async def enable_skill(
            skill_name: str, token: str = Depends(verify_api_key),
        ) -> SkillActionResponse:
            ok = self._db.set_skill_enabled(skill_name, True)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
            # Sync to runtime
            runtime = getattr(self, "_skill_runtime", None)
            if runtime:
                runtime.set_skill_enabled(skill_name, True)
            return SkillActionResponse(status="enabled")

        @app.post("/api/v1/skills/{skill_name}/disable", response_model=SkillActionResponse)
        async def disable_skill(
            skill_name: str, token: str = Depends(verify_api_key),
        ) -> SkillActionResponse:
            ok = self._db.set_skill_enabled(skill_name, False)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
            # Sync to runtime
            runtime = getattr(self, "_skill_runtime", None)
            if runtime:
                runtime.set_skill_enabled(skill_name, False)
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

            Sends the user message to the LLM router with memory context,
            conversation history, and streams the response token by token.
            Persists all messages to DB for session continuity.
            """
            session_id = body.session_id or "default"

            async def event_generator() -> Any:
                # ── 1. Persist user message ──
                try:
                    self._db.save_chat_message(session_id, "user", body.message)
                except Exception as e:
                    logger.warning(f"Failed to save user message: {e}")

                # ── 2. Gather memory context ──
                memory_context = ""
                if self._memory and body.message.strip():
                    results = self._memory.search(body.message, max_results=5)
                    if results:
                        snippets = []
                        for doc in results:
                            snippet = doc.text[:300].strip()
                            if doc.source:
                                snippet = f"[{doc.source_type or 'memory'}] {snippet}"
                            snippets.append(snippet)
                        memory_context = (
                            "\n\n---\n**Your memories relevant to this question:**\n"
                            + "\n".join(f"- {s}" for s in snippets)
                        )

                # ── 3. Build system prompt ──
                system = self._system_prompt

                # Inject current date/time so the LLM never hallucinates it
                from datetime import datetime
                now = datetime.now()
                system += (
                    f"\n\n## Current Date & Time\n"
                    f"Today is {now.strftime('%A, %B %d, %Y')}. "
                    f"Current time: {now.strftime('%H:%M')} (local)."
                )

                user_name = self._db.get_preference("user_name", "")
                if user_name:
                    system += f"\n\nThe user's name is {user_name}."
                if memory_context:
                    system += memory_context

                # ── 3b. Query Skills via match_ask ──
                skill_context = ""
                runtime = getattr(self, "_skill_runtime", None)
                if runtime and body.message.strip():
                    try:
                        skill_results = await runtime.match_ask(body.message)
                        if skill_results:
                            parts = []
                            for sr in skill_results:
                                skill_name = sr.get("skill", "unknown")
                                result = sr.get("result")
                                if result:
                                    parts.append(f"[Skill: {skill_name}]\n{result}")
                            if parts:
                                skill_context = (
                                    "\n\n---\n**Active Skills provided this information:**\n"
                                    + "\n\n".join(parts)
                                )
                    except Exception as e:
                        logger.warning(f"Skill match_ask failed: {e}")

                if skill_context:
                    system += skill_context

                # ── 4. Build messages with conversation history ──
                messages: list[dict[str, str]] = []
                try:
                    history = self._db.get_chat_messages(session_id, limit=20)
                    # Exclude the message we just saved (last user msg)
                    for msg in history[:-1]:
                        messages.append({"role": msg["role"], "content": msg["content"]})
                except Exception:
                    pass
                # Always append current user message as the last one
                messages.append({"role": "user", "content": body.message})

                # ── 5. Stream from LLM or fallback ──
                full_response = ""
                total_input_tokens = 0
                total_output_tokens = 0

                if self._router:
                    try:
                        async for chunk in self._router.stream(
                            messages=messages,
                            system=system,
                        ):
                            if chunk.content:
                                full_response += chunk.content
                                data = json.dumps({"type": "token", "content": chunk.content})
                                yield f"data: {data}\n\n"
                            if chunk.input_tokens:
                                total_input_tokens += chunk.input_tokens
                            if chunk.output_tokens:
                                total_output_tokens += chunk.output_tokens
                            if chunk.done:
                                break
                    except Exception as e:
                        logger.error(f"LLM streaming failed: {e}")
                        error_msg = "I'm having trouble connecting to the AI service right now. Please try again in a moment."
                        data = json.dumps({"type": "token", "content": error_msg})
                        yield f"data: {data}\n\n"
                        full_response = error_msg
                else:
                    # No router — fallback to memory-only response
                    if memory_context:
                        fallback = "Based on what I remember:\n"
                        for doc in (self._memory.search(body.message, max_results=3) if self._memory else []):
                            fallback += f"\n- {doc.text[:200]}"
                    else:
                        fallback = "Ciao! I'm OmniBrain. I'm awake but the LLM router isn't configured yet. Check your API keys in .env."
                    words = fallback.split()
                    for i, word in enumerate(words):
                        tok = word + (" " if i < len(words) - 1 else "")
                        data = json.dumps({"type": "token", "content": tok})
                        yield f"data: {data}\n\n"
                        await asyncio.sleep(0.02)
                    full_response = fallback

                # ── 6. Persist assistant response ──
                if full_response.strip():
                    try:
                        self._db.save_chat_message(session_id, "assistant", full_response)
                    except Exception as e:
                        logger.warning(f"Failed to save assistant message: {e}")

                # ── 7. Store conversation in memory ──
                if self._memory and body.message.strip() and full_response.strip():
                    try:
                        self._memory.store(
                            text=f"User: {body.message}\nAssistant: {full_response[:500]}",
                            source="chat",
                            source_type="conversation",
                            metadata={"session_id": session_id},
                        )
                    except Exception as e:
                        logger.warning(f"Failed to store chat in memory: {e}")

                # ── 8. Observe action for pattern detection ──
                pd = getattr(self, "_pattern_detector", None)
                if pd:
                    try:
                        pd.observe_action(
                            action_type="chat",
                            description=f"User asked: {body.message[:100]}",
                            context={"session_id": session_id},
                        )
                    except Exception:
                        pass

                # ── 8b. Extract structured data from conversation ──
                if self._router and body.message.strip() and full_response.strip():
                    try:
                        from omnibrain.conversation_extractor import extract_and_persist

                        asyncio.get_event_loop().create_task(
                            extract_and_persist(
                                user_message=body.message,
                                assistant_response=full_response,
                                router=self._router,
                                db=self._db,
                                memory=self._memory,
                                session_id=session_id,
                            )
                        )
                    except Exception as e:
                        logger.debug("Extraction task launch failed: %s", e)

                # ── 9. Track LLM cost ──
                if total_input_tokens or total_output_tokens:
                    try:
                        # Estimate cost using DeepSeek pricing as default
                        cost_in = total_input_tokens * 0.00014 / 1000
                        cost_out = total_output_tokens * 0.00028 / 1000
                        call_cost = cost_in + cost_out
                        month_cost = float(self._db.get_preference("llm_month_cost", "0") or "0")
                        month_calls = int(self._db.get_preference("llm_month_calls", "0") or "0")
                        self._db.set_preference(
                            "llm_month_cost",
                            str(round(month_cost + call_cost, 6)),
                            learned_from="cost_tracker",
                        )
                        self._db.set_preference(
                            "llm_month_calls",
                            str(month_calls + 1),
                            learned_from="cost_tracker",
                        )
                    except Exception:
                        pass

                # ── 10. Done signal ──
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

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
        # Chat history & session management
        # ══════════════════════════════════════════════════════════════════

        @app.get("/api/v1/chat/sessions")
        async def get_chat_sessions(
            limit: int = Query(20, ge=1, le=100),
            token: str = Depends(verify_api_key),
        ) -> dict[str, Any]:
            """List recent chat sessions."""
            sessions = self._db.get_chat_sessions(limit)
            return {"sessions": sessions}

        @app.get("/api/v1/chat/history")
        async def get_chat_history(
            session_id: str = Query("default"),
            limit: int = Query(100, ge=1, le=500),
            token: str = Depends(verify_api_key),
        ) -> dict[str, Any]:
            """Get chat messages for a session."""
            messages = self._db.get_chat_messages(session_id, limit)
            return {"session_id": session_id, "messages": messages}

        @app.delete("/api/v1/chat/sessions/{session_id}")
        async def delete_chat_session(
            session_id: str,
            token: str = Depends(verify_api_key),
        ) -> dict[str, Any]:
            """Delete a chat session."""
            deleted = self._db.delete_chat_session(session_id)
            return {"ok": True, "deleted": deleted}

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

            # ── Persist raw Google data that was previously discarded ──
            try:
                import json as _json
                # Persist emails as events
                for em in result.raw_emails:
                    subject = getattr(em, "subject", "") or ""
                    snippet = getattr(em, "snippet", "") or getattr(em, "body", "")[:500] if hasattr(em, "body") else ""
                    sender = getattr(em, "sender", "")
                    ts = getattr(em, "date", None) or getattr(em, "timestamp", None)
                    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None
                    self._db.insert_event(
                        source="gmail",
                        event_type="email",
                        title=subject or "(no subject)",
                        content=snippet,
                        metadata=_json.dumps({"sender": sender, "from_onboarding": True}),
                        timestamp=ts_str,
                    )
                # Persist calendar events
                for ev in result.raw_events:
                    title = getattr(ev, "title", "") or getattr(ev, "summary", "") or ""
                    start = getattr(ev, "start_time", None) or getattr(ev, "start", None)
                    end = getattr(ev, "end_time", None) or getattr(ev, "end", None)
                    attendees = getattr(ev, "attendees", [])
                    ts_str = start.isoformat() if hasattr(start, "isoformat") else str(start) if start else None
                    self._db.insert_event(
                        source="calendar",
                        event_type="meeting",
                        title=title or "(untitled event)",
                        metadata=_json.dumps({
                            "start_time": start.isoformat() if hasattr(start, "isoformat") else str(start or ""),
                            "end_time": end.isoformat() if hasattr(end, "isoformat") else str(end or ""),
                            "attendees": _json.dumps(list(attendees) if attendees else []),
                            "from_onboarding": True,
                        }),
                        timestamp=ts_str,
                    )
                # Persist contacts
                for contact_email in result.raw_contacts:
                    if contact_email and "@" in contact_email:
                        from omnibrain.models import ContactInfo
                        self._db.upsert_contact(ContactInfo(
                            email=contact_email,
                            name=contact_email.split("@")[0].replace(".", " ").title(),
                            source="gmail",
                        ))
                if result.raw_emails or result.raw_events:
                    logger.info(
                        "Onboarding: persisted %d emails, %d events, %d contacts",
                        len(result.raw_emails), len(result.raw_events), len(result.raw_contacts),
                    )
            except Exception as e:
                logger.warning("Failed to persist onboarding raw data: %s", e)

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
        # Onboarding — conversational profile save
        # ══════════════════════════════════════════════════════════════════

        @app.post("/api/v1/onboarding/profile")
        async def onboarding_save_profile(
            body: OnboardingProfileRequest,
            token: str = Depends(verify_api_key),
        ) -> dict[str, Any]:
            """Save profile info from conversational onboarding (no Google needed)."""
            saved: dict[str, str] = {}

            if body.name:
                self._db.set_preference("user_name", body.name, learned_from="onboarding_chat")
                saved["name"] = body.name
            if body.work:
                self._db.set_preference("user_work", body.work, learned_from="onboarding_chat")
                saved["work"] = body.work
            if body.goals:
                self._db.set_preference("user_goals", body.goals, learned_from="onboarding_chat")
                saved["goals"] = body.goals
            if body.timezone:
                self._db.set_preference("timezone", body.timezone, learned_from="onboarding_chat")
                saved["timezone"] = body.timezone

            # Also store in memory for the LLM to reference
            if self._memory:
                profile_parts = []
                if body.name:
                    profile_parts.append(f"The user's name is {body.name}.")
                if body.work:
                    profile_parts.append(f"They work on: {body.work}.")
                if body.goals:
                    profile_parts.append(f"Their goals: {body.goals}.")
                if profile_parts:
                    self._memory.store(
                        text=" ".join(profile_parts),
                        source="onboarding",
                        source_type="profile",
                    )

            self._db.set_preference("onboarding_complete", True, learned_from="onboarding_chat")

            # ── Extract structured data from interview answers ──
            # Run LLM extraction on the profile to populate events table
            # so the briefing has data from day zero.
            if self._router and (body.work or body.goals):
                try:
                    from omnibrain.conversation_extractor import extract_and_persist

                    profile_text = []
                    if body.name:
                        profile_text.append(f"My name is {body.name}.")
                    if body.work:
                        profile_text.append(f"I work on: {body.work}.")
                    if body.goals:
                        profile_text.append(f"What I wish I had more time for: {body.goals}.")

                    user_msg = " ".join(profile_text)
                    assistant_msg = f"Welcome {body.name or 'there'}! I've saved your profile."

                    asyncio.get_event_loop().create_task(
                        extract_and_persist(
                            user_message=user_msg,
                            assistant_response=assistant_msg,
                            router=self._router,
                            db=self._db,
                            memory=self._memory,
                            session_id="onboarding",
                        )
                    )
                except Exception as e:
                    logger.debug("Onboarding extraction failed: %s", e)

            return {"ok": True, "saved": saved}

        # ══════════════════════════════════════════════════════════════════
        # Knowledge Graph — cross-source queries
        # ══════════════════════════════════════════════════════════════════

        @app.get("/api/v1/knowledge/query")
        async def knowledge_query(
            q: str = "",
            token: str = Depends(verify_api_key),
        ) -> dict[str, Any]:
            """Query the knowledge graph with natural language."""
            kg = getattr(self, "_knowledge_graph", None)
            if not kg:
                return {"summary": "", "references": [], "error": "Knowledge graph not available"}
            if not q.strip():
                return {"summary": "", "references": [], "error": "Empty query"}
            try:
                result = kg.query(q.strip())
                return {
                    "summary": result.summary,
                    "references": [s.to_dict() for s in result.references[:10]],
                    "source_count": result.source_count,
                }
            except Exception as e:
                logger.warning("Knowledge query failed: %s", e)
                return {"summary": "", "references": [], "error": str(e)}

        @app.get("/api/v1/knowledge/contact/{identifier}")
        async def knowledge_contact(
            identifier: str,
            token: str = Depends(verify_api_key),
        ) -> dict[str, Any]:
            """Get contact summary from knowledge graph."""
            kg = getattr(self, "_knowledge_graph", None)
            if not kg:
                return {"error": "Knowledge graph not available"}
            try:
                return kg.get_contact_summary(identifier)
            except Exception as e:
                logger.warning("Contact summary failed: %s", e)
                return {"error": str(e)}

        # ══════════════════════════════════════════════════════════════════
        # Patterns — detected patterns + automation proposals
        # ══════════════════════════════════════════════════════════════════

        @app.get("/api/v1/patterns")
        async def get_patterns(
            token: str = Depends(verify_api_key),
        ) -> dict[str, Any]:
            """Get detected patterns and automation proposals."""
            pd = getattr(self, "_pattern_detector", None)
            if not pd:
                return {"patterns": [], "automations": [], "summary": {}}
            try:
                patterns = pd.get_patterns()
                strong = pd.get_strong_patterns()
                automations = pd.propose_automations()
                summary = pd.summary()
                return {
                    "patterns": [
                        {
                            "type": p.pattern_type,
                            "description": p.description,
                            "occurrences": p.occurrence_count,
                            "confidence": round(p.avg_confidence, 2),
                            "strength": p.strength,
                            "first_seen": p.first_seen,
                            "last_seen": p.last_seen,
                        }
                        for p in patterns
                    ],
                    "strong_patterns": [
                        {"type": p.pattern_type, "description": p.description, "strength": p.strength}
                        for p in strong
                    ],
                    "automations": [
                        {
                            "title": a.title,
                            "description": a.description,
                            "pattern_type": a.pattern_type,
                            "confidence": round(a.confidence, 2),
                        }
                        for a in automations
                    ],
                    "summary": summary,
                }
            except Exception as e:
                logger.warning("Patterns fetch failed: %s", e)
                return {"patterns": [], "automations": [], "summary": {}, "error": str(e)}

        @app.get("/api/v1/patterns/weekly")
        async def get_patterns_weekly(
            token: str = Depends(verify_api_key),
        ) -> dict[str, Any]:
            """Get weekly pattern analysis."""
            pd = getattr(self, "_pattern_detector", None)
            if not pd:
                return {"analysis": {}}
            try:
                return {"analysis": pd.weekly_analysis()}
            except Exception as e:
                logger.warning("Weekly patterns failed: %s", e)
                return {"analysis": {}, "error": str(e)}

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
    Creates and wires: DB, MemoryManager, BriefingGenerator, LLMRouter,
    ProactiveEngine (with PriorityScorer + PatternDetector), WebSocket broadcast.
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

    # Create LLM router — uses DeepSeek as primary (cheapest + fast)
    router = None
    try:
        import os
        if os.environ.get("DEEPSEEK_API_KEY"):
            router = LLMRouter(primary=Provider.DEEPSEEK)
            logger.info("LLM router initialized with DeepSeek as primary")
        elif os.environ.get("OPENAI_API_KEY"):
            router = LLMRouter(primary=Provider.OPENAI)
            logger.info("LLM router initialized with OpenAI as primary")
        elif os.environ.get("ANTHROPIC_API_KEY"):
            router = LLMRouter(primary=Provider.CLAUDE)
            logger.info("LLM router initialized with Claude as primary")
        else:
            logger.warning("No LLM API key found — chat will use fallback mode")
    except Exception as e:
        logger.warning(f"Failed to create LLM router: {e}")

    briefing_gen = None
    if memory:
        from omnibrain.briefing import BriefingGenerator
        briefing_gen = BriefingGenerator(db, memory, router=router)

    # ── Wire ProactiveEngine + PriorityScorer + PatternDetector ──
    engine = None
    pattern_detector = None
    knowledge_graph = None
    review_engine = None
    try:
        from omnibrain.proactive.engine import ProactiveEngine
        from omnibrain.proactive.patterns import PatternDetector

        pattern_detector = PatternDetector(db)

        # Wire ReviewEngine — 693 LOC of evening/weekly review logic
        try:
            from omnibrain.review_engine import ReviewEngine
            review_engine = ReviewEngine(db, memory)
            logger.info("ReviewEngine wired")
        except Exception as e:
            logger.warning(f"Failed to create ReviewEngine: {e}")

        engine = ProactiveEngine(db, config)
        engine.register_defaults(
            briefing_generator=briefing_gen,
            memory_manager=memory,
            review_engine=review_engine,
            pattern_detector=pattern_detector,
        )

        # Wire KnowledgeGraph — 706 LOC of cross-source query logic
        if memory:
            try:
                from omnibrain.knowledge_graph import KnowledgeGraph
                knowledge_graph = KnowledgeGraph(db, memory)
                logger.info("KnowledgeGraph wired")
            except Exception as e:
                logger.warning(f"Failed to create KnowledgeGraph: {e}")

        logger.info("ProactiveEngine + PatternDetector wired")
    except Exception as e:
        logger.warning(f"Failed to create ProactiveEngine: {e}")

    # ── Wire SkillRuntime + EventBus ──
    event_bus = EventBus()
    skill_runtime: SkillRuntime | None = None
    try:
        skill_runtime = SkillRuntime(
            db=db,
            memory=memory,
            knowledge_graph=knowledge_graph,
            approval_gate=None,
            config=config,
            event_bus=event_bus,
            llm_router=router,
        )
        project_root = Path(__file__).resolve().parent.parent.parent
        skill_dirs = [project_root / "skills", actual_dir / "skills"]
        discovered = skill_runtime.discover(skill_dirs)

        # Auto-register discovered skills in DB so they appear in the UI
        for manifest in discovered:
            existing = db.get_installed_skill(manifest.name)
            if not existing:
                db.install_skill(
                    name=manifest.name,
                    version=manifest.version,
                    description=manifest.description,
                    author=manifest.author,
                    category=manifest.category,
                    permissions=manifest.permissions,
                )
                logger.info(f"Auto-registered skill '{manifest.name}' in DB")

        logger.info(f"SkillRuntime wired — {len(discovered)} skills discovered")
    except Exception as e:
        logger.warning(f"Failed to create SkillRuntime: {e}")

    server = OmniBrainAPIServer(
        db=db,
        memory_manager=memory,
        briefing_gen=briefing_gen,
        engine_status_fn=engine.get_status if engine else None,
        auth_token=auth_token,
        version=version,
        data_dir=actual_dir,
        router=router,
    )

    # Store references on server for access in endpoints
    server._engine = engine  # type: ignore[attr-defined]
    server._pattern_detector = pattern_detector  # type: ignore[attr-defined]
    server._skill_runtime = skill_runtime  # type: ignore[attr-defined]
    server._event_bus = event_bus  # type: ignore[attr-defined]
    server._knowledge_graph = knowledge_graph  # type: ignore[attr-defined]

    # ── Wire EventBus "notification" → WebSocket broadcast ──
    async def _event_bus_to_ws(event_type: str, data: dict[str, Any]) -> None:
        """Bridge EventBus notifications → WebSocket broadcast."""
        await server.broadcast("notification", data)

    event_bus.subscribe("notification", _event_bus_to_ws)

    # ── Wire ProactiveEngine notify → WebSocket broadcast ──
    if engine:
        _loop_ref: asyncio.AbstractEventLoop | None = None

        def _notify_via_ws(level: str, title: str, message: str) -> None:
            """Bridge sync notify callback → async WebSocket broadcast."""
            payload = {
                "level": level,
                "title": title,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
            try:
                loop = _loop_ref or asyncio.get_running_loop()
                loop.create_task(server.broadcast("notification", payload))
            except RuntimeError:
                logger.debug("No event loop for WS broadcast (probably testing)")

        engine.set_notify_callback(_notify_via_ws)

        # Start engine as a background task on FastAPI startup
        @server.app.on_event("startup")
        async def _start_proactive_engine() -> None:
            nonlocal _loop_ref
            _loop_ref = asyncio.get_running_loop()
            asyncio.create_task(engine.run())
            logger.info("ProactiveEngine started as background task")

        @server.app.on_event("shutdown")
        async def _stop_proactive_engine() -> None:
            await engine.stop()
            logger.info("ProactiveEngine stopped")

    # ── Start SkillRuntime as background task ──
    if skill_runtime:
        @server.app.on_event("startup")
        async def _start_skill_runtime() -> None:
            asyncio.create_task(skill_runtime.run())  # type: ignore[union-attr]
            logger.info("SkillRuntime started as background task")

        @server.app.on_event("shutdown")
        async def _stop_skill_runtime() -> None:
            await skill_runtime.stop()  # type: ignore[union-attr]
            logger.info("SkillRuntime stopped")

    return server
