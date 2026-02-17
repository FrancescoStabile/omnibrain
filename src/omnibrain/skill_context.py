"""
OmniBrain — Skill Context

The sandboxed interface between a Skill and the Core.
Every Skill handler receives a SkillContext — it is the ONLY way
Skills interact with memory, LLM, notifications, and proposals.

Permission checking is enforced at this level.  A Skill that
declares ``permissions: [read_memory, notify]`` in its manifest
can only call methods guarded by those two permissions.

Design:
    - Created per-invocation by SkillRuntime
    - Holds references to core services (DB, memory, approval, …)
    - Every public method checks ``_require(permission)`` first
    - Lightweight — no long-lived state beyond the invocation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator

logger = logging.getLogger("omnibrain.skill_context")


# ─── Permission Denied ───────────────────────────────────────────────────


class PermissionDenied(Exception):
    """Raised when a Skill calls an API it has no permission for."""


# ─── Notification levels (re-exported for handler convenience) ───────────


class NotifyLevel:
    SILENT = "silent"
    FYI = "fyi"
    IMPORTANT = "important"
    CRITICAL = "critical"


# ─── SkillContext ─────────────────────────────────────────────────────────


class SkillContext:
    """The sandbox interface between a Skill and OmniBrain core.

    Attributes:
        skill_name:   Identifier of the invoking Skill.
        permissions:  Set of granted permission strings.

    Usage inside a handler::

        async def handle(ctx: SkillContext) -> None:
            results = await ctx.memory_search("project update")
            await ctx.notify("Found something!", level="FYI")
    """

    def __init__(
        self,
        skill_name: str,
        permissions: set[str],
        *,
        db: Any = None,
        memory: Any = None,
        knowledge_graph: Any = None,
        approval_gate: Any = None,
        config: Any = None,
        event_bus: Any = None,
        llm_router: Any = None,
    ) -> None:
        self.skill_name = skill_name
        self.permissions = frozenset(permissions)

        # Core service references (injected by SkillRuntime)
        self._db = db
        self._memory = memory
        self._llm_router = llm_router
        self._kg = knowledge_graph
        self._approval = approval_gate
        self._config = config
        self._event_bus = event_bus

        # Invocation-local log buffer
        self._log_buffer: list[dict[str, str]] = []

        # Integration client cache (per-invocation)
        self._integration_cache: dict[str, Any] = {}

    # ──────────────────────────────────────────────────────────
    # Permission guard
    # ──────────────────────────────────────────────────────────

    def _require(self, permission: str) -> None:
        """Raise ``PermissionDenied`` if the Skill lacks *permission*."""
        if permission not in self.permissions:
            raise PermissionDenied(
                f"Skill '{self.skill_name}' lacks permission '{permission}'"
            )

    def has_permission(self, permission: str) -> bool:
        """Check whether this context has a given permission."""
        return permission in self.permissions

    # ──────────────────────────────────────────────────────────
    # Memory  (read_memory / write_memory)
    # ──────────────────────────────────────────────────────────

    async def memory_search(
        self,
        query: str,
        limit: int = 10,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search the user's memory store.

        Returns list of dicts with keys: id, text, source, score.
        """
        self._require("read_memory")
        if not self._memory:
            return []
        docs = self._memory.search(
            query,
            max_results=limit,
            source_filter=source or "all",
        )
        return [d.to_dict() for d in docs]

    async def memory_store(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a new entry in memory.  Returns the document ID."""
        self._require("write_memory")
        if not self._memory:
            return ""
        from omnibrain.memory import MemoryDocument

        doc = MemoryDocument(
            id=f"skill:{self.skill_name}:{datetime.now().isoformat()}",
            text=content,
            source=f"skill:{self.skill_name}",
            source_type="skill",
            metadata=metadata or {},
        )
        self._memory.store(doc)
        return doc.id

    # ──────────────────────────────────────────────────────────
    # Knowledge Graph  (read_memory — reuses same perm)
    # ──────────────────────────────────────────────────────────

    async def who_said_what(
        self, person: str, topic: str | None = None
    ) -> list[dict[str, Any]]:
        self._require("read_memory")
        if not self._kg:
            return []
        return self._kg.who_said_what(person, topic)

    async def correlate(self, topic_a: str, topic_b: str) -> list[dict[str, Any]]:
        self._require("read_memory")
        if not self._kg:
            return []
        return self._kg.correlate(topic_a, topic_b)

    async def get_contacts(self, query: str | None = None) -> list[dict[str, Any]]:
        """Return contacts, optionally filtered by *query*."""
        self._require("read_memory")
        if not self._db:
            return []
        contacts = self._db.get_contacts(limit=100)
        if query:
            q = query.lower()
            contacts = [
                c for c in contacts
                if q in c.name.lower() or q in c.email.lower()
            ]
        return [c.to_dict() for c in contacts]

    # ──────────────────────────────────────────────────────────
    # Notifications  (notify)
    # ──────────────────────────────────────────────────────────

    async def notify(self, message: str, level: str = "fyi") -> None:
        """Send a notification to the user."""
        self._require("notify")
        logger.info(
            f"[{self.skill_name}] notify({level}): {message[:120]}"
        )
        if self._event_bus is not None:
            await self._event_bus.emit(
                "notification",
                {
                    "skill": self.skill_name,
                    "message": message,
                    "level": level,
                    "timestamp": datetime.now().isoformat(),
                },
            )

    # ──────────────────────────────────────────────────────────
    # Proposals  (notify — proposals are a kind of notification)
    # ──────────────────────────────────────────────────────────

    async def propose_action(
        self,
        type: str,
        title: str,
        description: str,
        action_data: dict[str, Any] | None = None,
        priority: int = 2,
    ) -> int:
        """Propose an action that needs user approval.

        Returns the proposal ID.
        """
        self._require("notify")
        if not self._db:
            return 0
        proposal_id = self._db.insert_proposal(
            type=type,
            title=f"[{self.skill_name}] {title}",
            description=description,
            action_data=action_data or {},
            priority=priority,
        )
        logger.info(
            f"[{self.skill_name}] proposed action: {title} (id={proposal_id})"
        )
        return proposal_id

    async def get_proposal_status(self, proposal_id: int) -> str:
        """Check the status of a previously created proposal."""
        if not self._db:
            return "unknown"
        row = None
        try:
            from contextlib import suppress
            with suppress(Exception):
                proposals = self._db.get_pending_proposals()
                for p in proposals:
                    if p.get("id") == proposal_id:
                        row = p
                        break
        except Exception:
            pass
        if row:
            return row.get("status", "unknown")
        return "unknown"

    # ──────────────────────────────────────────────────────────
    # LLM  (llm_access)
    # ──────────────────────────────────────────────────────────

    async def llm_complete(
        self,
        prompt: str,
        task_type: str = "quick",
    ) -> str:
        """Request an LLM completion.

        *task_type* maps to the LLM router's model selection:
        ``"quick"`` → DeepSeek, ``"reasoning"`` → Claude, etc.
        """
        self._require("llm_access")
        logger.info(f"[{self.skill_name}] llm_complete(task={task_type}, len={len(prompt)})")
        if not self._llm_router:
            logger.warning(f"[{self.skill_name}] llm_complete: no router available")
            return ""
        try:
            messages = [{"role": "user", "content": prompt}]
            full = ""
            async for chunk in self._llm_router.stream(
                messages=messages,
                system=f"You are helping the '{self.skill_name}' skill. Be concise and factual.",
            ):
                if chunk.content:
                    full += chunk.content
                if chunk.done:
                    break
            return full
        except Exception as e:
            logger.error(f"[{self.skill_name}] llm_complete failed: {e}")
            return ""

    async def llm_stream(
        self,
        prompt: str,
        task_type: str = "quick",
    ) -> AsyncIterator[str]:
        """Streaming LLM completion (async generator)."""
        self._require("llm_access")
        if not self._llm_router:
            logger.warning(f"[{self.skill_name}] llm_stream: no router available")
            yield ""
            return
        try:
            messages = [{"role": "user", "content": prompt}]
            async for chunk in self._llm_router.stream(
                messages=messages,
                system=f"You are helping the '{self.skill_name}' skill. Be concise and factual.",
            ):
                if chunk.content:
                    yield chunk.content
                if chunk.done:
                    break
        except Exception as e:
            logger.error(f"[{self.skill_name}] llm_stream failed: {e}")
            yield ""

    # ──────────────────────────────────────────────────────────
    # User properties  (read_profile)
    # ──────────────────────────────────────────────────────────

    @property
    def user_name(self) -> str:
        if self._config:
            return str(getattr(self._config, "user_name", "User"))
        return "User"

    @property
    def user_preferences(self) -> dict[str, Any]:
        if self._db:
            return self._db.get_all_preferences()
        return {}

    @property
    def user_timezone(self) -> str:
        if self._config:
            return str(getattr(self._config, "timezone", "UTC"))
        return "UTC"

    # ──────────────────────────────────────────────────────────
    # Skill-Local Storage  (skill_data — auto-granted)
    # ──────────────────────────────────────────────────────────

    async def get_data(self, key: str, default: Any = None) -> Any:
        """Read from skill-local key-value store."""
        if not self._db:
            return default
        return self._db.get_preference(
            f"skill:{self.skill_name}:{key}", default
        )

    async def set_data(self, key: str, value: Any) -> None:
        """Write to skill-local key-value store."""
        if not self._db:
            return
        self._db.set_preference(
            f"skill:{self.skill_name}:{key}",
            value,
            confidence=1.0,
            learned_from=f"skill:{self.skill_name}",
        )

    async def delete_data(self, key: str) -> None:
        """Delete a key from skill-local storage."""
        if not self._db:
            return
        try:
            self._db.delete_preference(f"skill:{self.skill_name}:{key}")
        except Exception as e:
            logger.warning(f"[{self.skill_name}] delete_data failed: {e}")

    # ──────────────────────────────────────────────────────────
    # Integration Access  (google_gmail / read_calendar)
    # ──────────────────────────────────────────────────────────

    _INTEGRATION_PERMISSIONS: dict[str, str] = {
        "gmail": "google_gmail",
        "calendar": "read_calendar",
    }

    def _get_data_dir(self) -> "Path":
        """Resolve data_dir from config or fall back to ~/.omnibrain."""
        from pathlib import Path

        if self._config:
            dd = getattr(self._config, "data_dir", None)
            if dd:
                return Path(dd) if not isinstance(dd, Path) else dd
        return Path.home() / ".omnibrain"

    def get_integration(self, name: str) -> Any:
        """Return an authenticated integration client.

        Supported integrations:
            ``"gmail"``    → ``GmailClient``    (requires ``google_gmail``)
            ``"calendar"`` → ``CalendarClient``  (requires ``read_calendar``)

        Raises ``PermissionDenied`` if the Skill lacks the needed permission.
        Returns ``None`` if the client cannot authenticate.
        """
        perm = self._INTEGRATION_PERMISSIONS.get(name)
        if perm is None:
            raise ValueError(
                f"Unknown integration '{name}'. "
                f"Available: {list(self._INTEGRATION_PERMISSIONS)}"
            )
        self._require(perm)

        # Cache per-invocation to avoid re-authenticating
        cache_key = f"{self.skill_name}:{name}"
        if cache_key in self._integration_cache:
            return self._integration_cache[cache_key]

        data_dir = self._get_data_dir()
        client: Any = None

        if name == "gmail":
            from omnibrain.integrations.gmail import GmailClient

            client = GmailClient(data_dir=data_dir)
            if not client.authenticate():
                logger.warning(f"[{self.skill_name}] Gmail authentication failed")
                return None

        elif name == "calendar":
            from omnibrain.integrations.calendar import CalendarClient

            client = CalendarClient(data_dir=data_dir)
            if not client.authenticate():
                logger.warning(f"[{self.skill_name}] Calendar authentication failed")
                return None

        if client is not None:
            self._integration_cache[cache_key] = client
        return client

    # ──────────────────────────────────────────────────────────
    # Events
    # ──────────────────────────────────────────────────────────

    async def emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event for other Skills to listen to."""
        if self._event_bus is not None:
            await self._event_bus.emit(event_type, {
                "skill": self.skill_name,
                **data,
            })

    # ──────────────────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────────────────

    def log(self, message: str, level: str = "info") -> None:
        """Structured log entry attributed to this Skill."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "skill": self.skill_name,
            "level": level,
            "message": message,
        }
        self._log_buffer.append(entry)
        getattr(logger, level, logger.info)(
            f"[{self.skill_name}] {message}"
        )


# ─── Event Bus ────────────────────────────────────────────────────────────


class EventBus:
    """Simple async pub/sub for inter-Skill and core events.

    Listeners are ``async def callback(event_type, data)`` coroutines.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Any]] = {}

    def subscribe(self, event_type: str, callback: Any) -> None:
        self._listeners.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Any) -> None:
        if event_type in self._listeners:
            self._listeners[event_type] = [
                cb for cb in self._listeners[event_type] if cb is not callback
            ]

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit *event_type* to all registered listeners."""
        for cb in self._listeners.get(event_type, []):
            try:
                await cb(event_type, data)
            except Exception as e:
                logger.warning(f"EventBus listener error on '{event_type}': {e}")

    @property
    def listener_count(self) -> int:
        return sum(len(v) for v in self._listeners.values())
