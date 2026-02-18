"""
OmniBrain — Conversation Extractor

After each chat exchange, an LLM call analyses the conversation and
extracts structured data:
    - Events / commitments  → `events` table (source="chat")
    - People mentioned       → `contacts` table (upsert)
    - Facts about the user   → `preferences` table
    - Action items           → `proposals` table (type="user_commitment")

The extraction runs as a background task (non-blocking) after the
streaming response has been fully delivered to the client.

Cost: ~$0.001 per extraction (DeepSeek).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("omnibrain.extractor")

# ═══════════════════════════════════════════════════════════════════════════
# Extraction prompt
# ═══════════════════════════════════════════════════════════════════════════

_EXTRACTION_SYSTEM = """\
You are a structured data extractor. Given a conversation between a user \
and an AI assistant, extract all actionable information.

Return ONLY a JSON object — no explanations, no markdown fences.

Schema:
{
  "events": [
    {
      "title": "short title",
      "date": "YYYY-MM-DD or null if unknown",
      "time": "HH:MM or null",
      "type": "meeting|deadline|reminder|commitment|appointment",
      "people": ["name1"],
      "description": "brief detail"
    }
  ],
  "contacts": [
    {
      "name": "Person Name",
      "relationship": "colleague|friend|family|client|other",
      "context": "what we know about them"
    }
  ],
  "user_facts": [
    {
      "key": "user_work|user_interest|user_habit|user_location|user_preference",
      "value": "the actual fact"
    }
  ],
  "action_items": [
    {
      "title": "what needs to be done",
      "deadline": "YYYY-MM-DD or null",
      "priority": 1-5
    }
  ]
}

Rules:
- Only extract what is EXPLICITLY stated or clearly implied.
- Do NOT hallucinate dates, times, or people.
- If nothing actionable, return {"events":[],"contacts":[],"user_facts":[],"action_items":[]}.
- Dates should be absolute (resolve "tomorrow", "next Tuesday", etc. using today's date).
- Keep titles concise (< 60 chars).
- If the assistant used tools to create, delete, or modify events, DO NOT re-extract those \
  events — they are already handled. Only extract NEW information not addressed by tool actions.
- Do NOT extract events that the assistant confirmed were already created, deleted, or updated.
"""


# ═══════════════════════════════════════════════════════════════════════════
# Main extraction function
# ═══════════════════════════════════════════════════════════════════════════


async def extract_and_persist(
    *,
    user_message: str,
    assistant_response: str,
    router: Any,  # LLMRouter
    db: Any,  # OmniBrainDB
    memory: Any | None = None,  # MemoryManager
    session_id: str = "default",
    sanitizer: Any | None = None,  # PromptSanitizer
) -> dict[str, int]:
    """Extract structured data from a conversation and persist it.

    Runs an LLM call, parses the JSON response, and writes to the
    appropriate database tables. Returns counts of extracted items.

    This should be called as a fire-and-forget asyncio task so it
    doesn't block the chat response.
    """
    if not router or not db:
        return {}

    # Skip very short / trivial exchanges
    if len(user_message.strip()) < 20:
        return {}

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # Strip any tool-status noise from the response before extraction
    import re
    clean_response = re.sub(r'_\[Executing:.*?\]_\s*', '', assistant_response)

    prompt = (
        f"Today is {now.strftime('%A, %B %d, %Y')}.\n\n"
        f"User: {user_message}\n\n"
        f"Assistant: {clean_response[:3000]}"
    )

    # Sanitize external content if sanitizer is available
    if sanitizer:
        try:
            result = sanitizer.sanitize(prompt, source="chat_extraction")
            if result.is_blocked:
                logger.warning("Extraction blocked by prompt injection defense: %s", result.reason)
                return {}
            prompt = result.safe_text
        except Exception as e:
            logger.debug("Sanitizer error: %s", e)

    try:
        # Call LLM for extraction
        raw = ""
        async for chunk in router.stream(
            messages=[{"role": "user", "content": prompt}],
            system=_EXTRACTION_SYSTEM,
        ):
            if chunk.content:
                raw += chunk.content
            if chunk.done:
                break

        # Parse JSON — handle common LLM quirks
        raw = raw.strip()
        if raw.startswith("```"):
            # Strip markdown code fences
            lines = raw.split("\n")
            raw = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        data = json.loads(raw)

        counts: dict[str, int] = {}

        # ── Persist events ──
        events = data.get("events", [])
        for ev in events:
            title = ev.get("title", "")
            if not title:
                continue
            date = ev.get("date") or today_str
            time_str = ev.get("time") or ""
            ev_type = ev.get("type", "commitment")
            people = ev.get("people", [])
            desc = ev.get("description", "")

            timestamp = f"{date}T{time_str}:00" if time_str else f"{date}T00:00:00"
            all_day = not bool(time_str)

            metadata = {
                "type": ev_type,
                "people": people,
                "start_time": timestamp,
                "extracted_from": "chat",
                "session_id": session_id,
                "all_day": all_day,
            }

            try:
                db.insert_event(
                    source="chat",
                    event_type=ev_type,
                    title=title,
                    content=desc or title,
                    metadata=metadata,
                    timestamp=timestamp,
                )
            except Exception as e:
                logger.warning("Failed to insert extracted event: %s", e)

        counts["events"] = len(events)

        # ── Persist contacts ──
        contacts = data.get("contacts", [])
        for c in contacts:
            name = c.get("name", "").strip()
            if not name:
                continue
            relationship = c.get("relationship", "other")
            context = c.get("context", "")

            try:
                db.upsert_contact_by_name(
                    name=name,
                    relationship=relationship,
                    notes=context,
                )
            except Exception as e:
                logger.warning("Failed to upsert contact '%s': %s", name, e)

        counts["contacts"] = len(contacts)

        # ── Persist user facts ──
        facts = data.get("user_facts", [])
        for f in facts:
            key = f.get("key", "")
            value = f.get("value", "")
            if not key or not value:
                continue

            try:
                db.set_preference(key, value, learned_from="chat_extraction")
            except Exception as e:
                logger.warning("Failed to set user fact '%s': %s", key, e)

        counts["user_facts"] = len(facts)

        # ── Persist action items as proposals (with dedup) ──
        actions = data.get("action_items", [])
        # Get existing pending proposals to avoid duplicates
        existing_titles: set[str] = set()
        try:
            pending = db.get_pending_proposals()
            existing_titles = {p.get("title", "").lower() for p in pending}
        except Exception:
            pass

        for a in actions:
            title = a.get("title", "")
            if not title:
                continue
            # Skip if a proposal with essentially the same title already exists
            if title.lower() in existing_titles:
                logger.debug("Skipping duplicate proposal: %s", title)
                continue
            deadline = a.get("deadline")
            priority = min(max(int(a.get("priority", 2)), 1), 5)

            try:
                db.insert_proposal(
                    type="user_commitment",
                    title=title,
                    description=f"Extracted from your conversation. Deadline: {deadline or 'none'}.",
                    priority=priority,
                    action_data={
                        "source": "chat_extraction",
                        "session_id": session_id,
                        "deadline": deadline,
                    },
                )
            except Exception as e:
                logger.warning("Failed to insert action item: %s", e)

        counts["action_items"] = len(actions)

        total = sum(counts.values())
        if total > 0:
            logger.info(
                "Extracted from chat: %d events, %d contacts, %d facts, %d actions",
                counts["events"],
                counts["contacts"],
                counts["user_facts"],
                counts["action_items"],
            )

        return counts

    except json.JSONDecodeError as e:
        logger.warning("Extraction JSON parse failed: %s — raw: %.200s", e, raw)
        return {}
    except Exception as e:
        logger.warning("Conversation extraction failed: %s", e)
        return {}
