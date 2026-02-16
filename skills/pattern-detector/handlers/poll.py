"""Pattern Detector — Schedule handler (poll.py).

Scans memory for recurring patterns and proposes automations.
Extracts logic from proactive/patterns.py's PatternDetector.
"""

from __future__ import annotations

from datetime import datetime, timedelta


async def handle(ctx) -> dict:
    """Detect behavioral patterns from memory and propose automations.

    Flow:
        1. Query recent memory entries grouped by source/type
        2. Detect time-based, communication, and action patterns
        3. Store confirmed patterns in skill data
        4. Propose automations for strong patterns
        5. Notify user about new discoveries
    """
    settings = ctx.user_preferences
    min_occurrences = int(settings.get(
        "skill:pattern-detector:min_occurrences", 3
    ) or 3)
    window_days = int(settings.get(
        "skill:pattern-detector:detection_window_days", 30
    ) or 30)

    # Gather recent activity from memory
    recent = await ctx.memory_search("", limit=100)
    if not recent:
        return {"status": "no_data", "patterns": 0, "proposals": 0}

    # Cluster observations
    clusters = _cluster_observations(recent, min_occurrences)

    # Load previously known patterns
    known_raw = await ctx.get_data("known_patterns", "[]")
    known_patterns = _parse_json(known_raw)

    # Detect new patterns
    new_patterns = []
    for cluster in clusters:
        pattern_id = f"{cluster['type']}:{cluster['key']}"
        if not any(p.get("id") == pattern_id for p in known_patterns):
            new_patterns.append({
                "id": pattern_id,
                "type": cluster["type"],
                "key": cluster["key"],
                "count": cluster["count"],
                "description": cluster["description"],
                "detected_at": datetime.now().isoformat(),
            })

    # Merge and save
    all_patterns = known_patterns + new_patterns
    await ctx.set_data("known_patterns", _to_json(all_patterns))
    await ctx.set_data("last_detection", datetime.now().isoformat())

    # Propose automations for strong patterns (≥2× min threshold)
    proposals_created = 0
    for pattern in new_patterns:
        if pattern["count"] >= min_occurrences * 2:
            await ctx.propose_action(
                type="automation",
                title=f"Automate: {pattern['description']}",
                description=(
                    f"I've detected a recurring pattern: {pattern['description']}. "
                    f"This has occurred {pattern['count']} times in the last {window_days} days. "
                    f"Would you like me to automate this?"
                ),
                action_data={"pattern_id": pattern["id"], "pattern": pattern},
                priority=2,
            )
            proposals_created += 1

    # Notify about new discoveries
    if new_patterns:
        summary = ", ".join(p["description"] for p in new_patterns[:3])
        suffix = f" and {len(new_patterns) - 3} more" if len(new_patterns) > 3 else ""
        await ctx.notify(
            f"Detected {len(new_patterns)} new pattern(s): {summary}{suffix}",
            level="fyi",
        )

    return {
        "status": "detected",
        "total_patterns": len(all_patterns),
        "new_patterns": len(new_patterns),
        "proposals": proposals_created,
    }


def _cluster_observations(entries: list[dict], min_count: int) -> list[dict]:
    """Group memory entries by source and detect recurring themes."""
    clusters: list[dict] = []

    # Group by source
    by_source: dict[str, int] = {}
    for entry in entries:
        source = entry.get("source", "unknown")
        by_source[source] = by_source.get(source, 0) + 1

    for source, count in by_source.items():
        if count >= min_count:
            clusters.append({
                "type": "source_frequency",
                "key": source,
                "count": count,
                "description": f"Frequent activity from {source} ({count} times)",
            })

    # Group by time-of-day pattern (if timestamps available)
    hour_counts: dict[int, int] = {}
    for entry in entries:
        ts = entry.get("timestamp") or entry.get("metadata", {}).get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                hour_counts[dt.hour] = hour_counts.get(dt.hour, 0) + 1
            except (ValueError, TypeError):
                pass

    for hour, count in hour_counts.items():
        if count >= min_count:
            period = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
            clusters.append({
                "type": "time_pattern",
                "key": f"hour_{hour}",
                "count": count,
                "description": f"Activity spike in the {period} around {hour}:00 ({count} times)",
            })

    # Group by keyword frequency in content
    word_freq: dict[str, int] = {}
    stop_words = {"the", "a", "an", "is", "was", "are", "in", "on", "at", "to", "for",
                  "of", "with", "and", "or", "from", "by", "this", "that", "it", "be"}
    for entry in entries:
        text = entry.get("text", "").lower()
        for word in text.split():
            word = word.strip(".,!?;:()[]{}\"'")
            if len(word) > 3 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1

    for word, count in sorted(word_freq.items(), key=lambda x: -x[1])[:5]:
        if count >= min_count * 2:
            clusters.append({
                "type": "recurring_topic",
                "key": word,
                "count": count,
                "description": f"Topic '{word}' appears frequently ({count} mentions)",
            })

    return clusters


def _parse_json(raw: str | list) -> list:
    """Safely parse JSON string or return list as-is."""
    if isinstance(raw, list):
        return raw
    import json
    try:
        return json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []


def _to_json(data: list) -> str:
    import json
    return json.dumps(data)
