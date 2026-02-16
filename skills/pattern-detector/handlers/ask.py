"""Pattern Detector — Ask handler.

Returns detected patterns and proposed automations to the user.
"""

from __future__ import annotations

import json


async def handle(ctx, query: str) -> dict:
    """Answer questions about detected patterns and automations.

    Reads from skill-local storage populated by poll.py and
    provides a natural-language summary via LLM when available.
    """
    q = query.lower()

    # Load stored patterns
    known_raw = await ctx.get_data("known_patterns", "[]")
    patterns = _parse_json(known_raw)
    last_detection = await ctx.get_data("last_detection", "never")

    if not patterns:
        return {
            "answer": (
                "No patterns detected yet. "
                "The pattern detector runs periodically — results should appear soon."
            ),
            "patterns": [],
            "last_detection": last_detection,
        }

    # Filter by type if user asks about a specific kind
    filtered = patterns
    if "time" in q or "when" in q or "schedule" in q:
        filtered = [p for p in patterns if p.get("type") == "time_pattern"] or patterns
    elif "topic" in q or "keyword" in q or "about" in q:
        filtered = [p for p in patterns if p.get("type") == "recurring_topic"] or patterns
    elif "source" in q or "where" in q or "from" in q:
        filtered = [p for p in patterns if p.get("type") == "source_frequency"] or patterns

    # Compose answer
    if ctx.has_permission("llm_access"):
        context = "\n".join(
            f"- [{p.get('type')}] {p.get('description')} (count: {p.get('count', '?')})"
            for p in filtered[:10]
        )
        prompt = (
            f"The user is asking about their detected behavioral patterns.\n\n"
            f"Patterns discovered:\n{context}\n\n"
            f"User query: {query}\n\n"
            f"Summarize the relevant patterns in a helpful, concise way."
        )
        answer = await ctx.llm_complete(prompt, task_type="reasoning")
        if answer:
            return {
                "answer": answer,
                "patterns": filtered[:10],
                "total": len(patterns),
                "last_detection": last_detection,
            }

    # Fallback: manual formatting
    lines = [f"Detected {len(patterns)} pattern(s) (last scan: {last_detection}):"]
    for p in filtered[:8]:
        lines.append(f"  • {p.get('description', p.get('id', 'unknown'))}")

    return {
        "answer": "\n".join(lines),
        "patterns": filtered[:10],
        "total": len(patterns),
        "last_detection": last_detection,
    }


def _parse_json(raw: str | list) -> list:
    """Safely parse JSON string or return list as-is."""
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []
