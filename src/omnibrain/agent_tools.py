"""
OmniBrain — Agent Tool Registry Builder

Factory function that creates a fully-wired ToolRegistry for OmniBrainAgent.

Merges three tool families into one registry:
    1. Chat tools (events, contacts, proposals, preferences)
    2. Domain tools (email, calendar, memory)
    3. Agent intrinsics (create_finding, submit_analysis — auto-registered by Agent)

Each handler is a closure that captures server-level dependencies (db, memory,
data_dir, calendar_client) so the Agent's ToolRegistry.call() just passes
the LLM's arguments through.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from omnigent.tools import ToolRegistry

logger = logging.getLogger("omnibrain.agent_tools")


# ═══════════════════════════════════════════════════════════════════════════
# Schema converter: OpenAI function-calling → Omnigent ToolRegistry schema
# ═══════════════════════════════════════════════════════════════════════════


def _openai_to_registry_schema(tool_def: dict) -> dict:
    """Convert OpenAI function-calling schema to Omnigent registry format.

    OpenAI:  {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    Omnigent: {"name": ..., "description": ..., "parameters": ...}
    """
    fn = tool_def.get("function", tool_def)
    return {
        "name": fn["name"],
        "description": fn.get("description", ""),
        "parameters": fn.get("parameters", {}),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Builder
# ═══════════════════════════════════════════════════════════════════════════


def build_omnibrain_tools(
    db: Any,
    memory: Any | None = None,
    data_dir: Path | None = None,
    calendar_client_factory: Any | None = None,
) -> ToolRegistry:
    """Build a ToolRegistry pre-populated with all OmniBrain domain tools.

    Args:
        db: OmniBrainDB instance for data access.
        memory: Optional MemoryManager for semantic search / storage.
        data_dir: Path to ~/.omnibrain data directory.
        calendar_client_factory: Callable that returns a CalendarClient (lazy).

    Returns:
        ToolRegistry ready to be passed to OmniBrainAgent.
    """
    registry = ToolRegistry()

    # ── 1. Chat tools (events, contacts, proposals, preferences) ──
    _register_chat_tools(registry, db, calendar_client_factory)

    # ── 2. Email tools (requires Gmail auth) ──
    if data_dir:
        _register_email_tools(registry, data_dir)

    # ── 3. Calendar tools (requires Google Calendar auth) ──
    if data_dir:
        _register_calendar_tools(registry, data_dir, db)

    # ── 4. Memory tools (search + observation storage) ──
    if memory:
        _register_memory_tools(registry, memory)

    logger.info(
        f"Agent ToolRegistry built: {len(registry.tools)} tools registered "
        f"({', '.join(sorted(registry.tools.keys()))})"
    )

    return registry


# ═══════════════════════════════════════════════════════════════════════════
# Chat Tools — events, contacts, proposals, preferences
# ═══════════════════════════════════════════════════════════════════════════


def _register_chat_tools(
    registry: ToolRegistry,
    db: Any,
    calendar_client_factory: Any | None,
) -> None:
    """Register the 10 chat tools from chat_tools.py."""
    from omnibrain.chat_tools import CHAT_TOOLS, execute_tool

    for tool_def in CHAT_TOOLS:
        schema = _openai_to_registry_schema(tool_def)
        tool_name = schema["name"]

        # Create a closure that captures the tool name and calls execute_tool
        def _make_handler(name: str) -> Any:
            async def handler(**kwargs: Any) -> str:
                cal = calendar_client_factory() if calendar_client_factory else None
                return await execute_tool(
                    db=db,
                    tool_name=name,
                    arguments=kwargs,
                    calendar_client=cal,
                )
            return handler

        registry.register(tool_name, _make_handler(tool_name), schema)


# ═══════════════════════════════════════════════════════════════════════════
# Email Tools — fetch, search, classify
# ═══════════════════════════════════════════════════════════════════════════


def _register_email_tools(registry: ToolRegistry, data_dir: Path) -> None:
    """Register email tools from tools/email_tools.py."""
    try:
        from omnibrain.tools.email_tools import (
            EMAIL_TOOL_SCHEMAS,
            classify_email,
            fetch_emails,
            search_emails,
        )
    except ImportError:
        logger.debug("Email tools not available (missing dependencies)")
        return

    # fetch_emails
    async def _fetch_emails(
        max_results: int = 20, query: str = "", since_hours: int = 24, **kw: Any,
    ) -> dict:
        result = fetch_emails(data_dir, max_results=max_results, query=query, since_hours=since_hours)
        return result  # ToolRegistry handles JSON serialization

    # search_emails
    async def _search_emails(query: str, max_results: int = 20, **kw: Any) -> dict:
        result = search_emails(data_dir, query=query, max_results=max_results)
        return result  # ToolRegistry handles JSON serialization

    # classify_email
    async def _classify_email(
        email_id: str, subject: str, sender: str = "", body_preview: str = "", **kw: Any,
    ) -> dict:
        result = classify_email(data_dir, email_id=email_id, subject=subject, sender=sender, body_preview=body_preview)
        return result  # ToolRegistry handles JSON serialization

    handlers = {
        "fetch_emails": _fetch_emails,
        "search_emails": _search_emails,
        "classify_email": _classify_email,
    }

    for schema in EMAIL_TOOL_SCHEMAS:
        name = schema["name"]
        if name in handlers:
            registry.register(name, handlers[name], schema)


# ═══════════════════════════════════════════════════════════════════════════
# Calendar Tools — today events, upcoming, meeting brief
# ═══════════════════════════════════════════════════════════════════════════


def _register_calendar_tools(
    registry: ToolRegistry, data_dir: Path, db: Any,
) -> None:
    """Register calendar tools from tools/calendar_tools.py."""
    try:
        from omnibrain.tools.calendar_tools import (
            CALENDAR_TOOL_SCHEMAS,
            generate_meeting_brief,
            get_today_events,
            get_upcoming_events,
        )
    except ImportError:
        logger.debug("Calendar tools not available (missing dependencies)")
        return

    async def _get_today(**kw: Any) -> dict:
        result = get_today_events(data_dir)
        return result  # ToolRegistry handles JSON serialization

    async def _get_upcoming(days: int = 7, max_results: int = 20, **kw: Any) -> dict:
        result = get_upcoming_events(data_dir, days=days, max_results=max_results)
        return result  # ToolRegistry handles JSON serialization

    async def _meeting_brief(event_id: str, **kw: Any) -> dict:
        result = generate_meeting_brief(data_dir, event_id=event_id, db=db)
        return result  # ToolRegistry handles JSON serialization

    handlers = {
        "get_today_events": _get_today,
        "get_upcoming_events": _get_upcoming,
        "generate_meeting_brief": _meeting_brief,
    }

    for schema in CALENDAR_TOOL_SCHEMAS:
        name = schema["name"]
        if name in handlers:
            registry.register(name, handlers[name], schema)


# ═══════════════════════════════════════════════════════════════════════════
# Memory Tools — search + observation
# ═══════════════════════════════════════════════════════════════════════════


def _register_memory_tools(registry: ToolRegistry, memory: Any) -> None:
    """Register memory tools from tools/memory_tools.py."""
    try:
        from omnibrain.tools.memory_tools import (
            SEARCH_MEMORY_SCHEMA,
            STORE_OBSERVATION_SCHEMA,
            search_memory,
            store_observation,
        )
    except ImportError:
        logger.debug("Memory tools not available (missing dependencies)")
        return

    async def _search(query: str, source_filter: str = "all", time_range_days: int = 90, **kw: Any) -> dict:
        result = search_memory(memory, {"query": query, "source_filter": source_filter, "time_range_days": time_range_days})
        return result

    async def _store_obs(
        pattern_type: str, description: str, evidence: str = "", confidence: float = 0.7, **kw: Any,
    ) -> dict:
        result = store_observation(memory, {
            "pattern_type": pattern_type,
            "description": description,
            "evidence": evidence,
            "confidence": confidence,
        })
        return result

    registry.register("search_memory", _search, SEARCH_MEMORY_SCHEMA)
    registry.register("store_observation", _store_obs, STORE_OBSERVATION_SCHEMA)
