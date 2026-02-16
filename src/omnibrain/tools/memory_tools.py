"""
OmniBrain — Memory Tools

Omnigent-compatible tool handlers for the memory system.

Tools:
    search_memory     — Semantic search across all OmniBrain memory
    store_observation — Record a pattern or observation about user behavior

Follows manifesto Section 7 (Memory Tools) schemas exactly.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("omnibrain.tools.memory")


# ═══════════════════════════════════════════════════════════════════════════
# Schemas (from manifesto Section 7)
# ═══════════════════════════════════════════════════════════════════════════

SEARCH_MEMORY_SCHEMA = {
    "name": "search_memory",
    "description": "Semantic search across all Omnibrain memory",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language search query"},
            "source_filter": {
                "type": "string",
                "enum": ["all", "email", "calendar", "github", "notes"],
                "default": "all",
                "description": "Filter results by source type",
            },
            "max_results": {
                "type": "integer",
                "default": 10,
                "description": "Maximum number of results to return",
            },
            "time_range_days": {
                "type": "integer",
                "default": 90,
                "description": "Only search within this many days",
            },
        },
        "required": ["query"],
    },
}

STORE_OBSERVATION_SCHEMA = {
    "name": "store_observation",
    "description": "Record a pattern or observation about user behavior",
    "parameters": {
        "type": "object",
        "properties": {
            "pattern_type": {
                "type": "string",
                "description": "Type of pattern (e.g., 'communication', 'scheduling', 'preference')",
            },
            "description": {
                "type": "string",
                "description": "Description of the observation",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "default": 0.5,
                "description": "Confidence score for this observation",
            },
        },
        "required": ["pattern_type", "description"],
    },
}

MEMORY_TOOL_SCHEMAS = [SEARCH_MEMORY_SCHEMA, STORE_OBSERVATION_SCHEMA]


# ═══════════════════════════════════════════════════════════════════════════
# Tool Handlers
# ═══════════════════════════════════════════════════════════════════════════


def search_memory(
    memory_manager: Any,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Search across all OmniBrain memory.

    Uses the MemoryManager to find relevant documents matching the query.
    Returns structured results for agent reasoning.

    Args:
        memory_manager: A MemoryManager instance.
        args: Tool arguments matching SEARCH_MEMORY_SCHEMA.

    Returns:
        Dict with results list, count, and backend info.
    """
    query = args.get("query", "")
    if not query:
        return {"results": [], "count": 0, "error": "Empty query"}

    source_filter = args.get("source_filter", "all")
    max_results = args.get("max_results", 10)
    time_range_days = args.get("time_range_days", 90)

    logger.info(
        f"Memory search: query='{query}', source={source_filter}, "
        f"max={max_results}, days={time_range_days}"
    )

    docs = memory_manager.search(
        query=query,
        max_results=max_results,
        source_filter=source_filter,
        time_range_days=time_range_days,
    )

    results = []
    for doc in docs:
        results.append({
            "id": doc.id,
            "text": doc.text,
            "source": doc.source,
            "source_type": doc.source_type,
            "timestamp": doc.timestamp,
            "score": round(doc.score, 4),
            "contacts": doc.contacts,
        })

    backend = "semantic" if memory_manager.has_chroma else "keyword"
    logger.info(f"Memory search returned {len(results)} results ({backend})")

    return {
        "results": results,
        "count": len(results),
        "query": query,
        "backend": backend,
    }


def store_observation(
    memory_manager: Any,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Store a pattern or observation about user behavior.

    Records observations from agent reasoning (e.g., "user prefers
    morning meetings", "user always replies to boss within 1 hour").

    Args:
        memory_manager: A MemoryManager instance.
        args: Tool arguments matching STORE_OBSERVATION_SCHEMA.

    Returns:
        Dict with stored observation details.
    """
    pattern_type = args.get("pattern_type", "")
    description = args.get("description", "")
    confidence = args.get("confidence", 0.5)

    if not pattern_type or not description:
        return {"stored": False, "error": "pattern_type and description required"}

    # Validate confidence
    confidence = max(0.0, min(1.0, float(confidence)))

    text = f"[{pattern_type}] {description}"
    doc_id = memory_manager.store(
        text=text,
        source="agent_observation",
        source_type="observation",
        metadata={
            "pattern_type": pattern_type,
            "confidence": confidence,
            "observed_at": datetime.now().isoformat(),
        },
    )

    logger.info(
        f"Stored observation: type={pattern_type}, "
        f"confidence={confidence}, id={doc_id}"
    )

    return {
        "stored": True,
        "id": doc_id,
        "pattern_type": pattern_type,
        "description": description,
        "confidence": confidence,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Batch Operations
# ═══════════════════════════════════════════════════════════════════════════


def ingest_emails_to_memory(
    memory_manager: Any,
    emails: list[dict[str, Any]],
) -> dict[str, Any]:
    """Batch ingest emails into memory store.

    Called during daemon collection to store fetched emails
    in the semantic memory for future search.

    Args:
        memory_manager: A MemoryManager instance.
        emails: List of email dicts from email_tools.

    Returns:
        Dict with ingestion stats.
    """
    stored = 0
    failed = 0

    for email_data in emails:
        try:
            memory_manager.store_email(email_data)
            stored += 1
        except Exception as e:
            logger.warning(f"Failed to ingest email: {e}")
            failed += 1

    logger.info(f"Ingested {stored}/{len(emails)} emails to memory")
    return {"stored": stored, "failed": failed, "total": len(emails)}


def ingest_events_to_memory(
    memory_manager: Any,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Batch ingest calendar events into memory store.

    Called during daemon collection to store fetched events
    in the semantic memory for future search.

    Args:
        memory_manager: A MemoryManager instance.
        events: List of event dicts from calendar_tools.

    Returns:
        Dict with ingestion stats.
    """
    stored = 0
    failed = 0

    for event_data in events:
        try:
            memory_manager.store_calendar_event(event_data)
            stored += 1
        except Exception as e:
            logger.warning(f"Failed to ingest event: {e}")
            failed += 1

    logger.info(f"Ingested {stored}/{len(events)} events to memory")
    return {"stored": stored, "failed": failed, "total": len(events)}
