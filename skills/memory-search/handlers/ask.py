"""Memory Search — Ask handler.

Searches across memory (FTS5) and knowledge graph (who_said_what, correlate),
then composes a natural-language answer via LLM if available.
"""

from __future__ import annotations


async def handle(ctx, query: str) -> dict:
    """Search the user's personal memory for answers.

    Flow:
        1. Full-text search in memory
        2. Knowledge graph query (who_said_what for person questions, correlate for topic links)
        3. Contact lookup for people-centric queries
        4. LLM-composed answer if available, else manual formatting
    """
    results = await ctx.memory_search(query, limit=15)

    # Detect person-centric query ("what did Marco say about...", "who said...")
    person, topic = _parse_person_topic(query)
    kg_results: list[dict] = []
    if person:
        kg_results = await ctx.who_said_what(person, topic)

    # Detect correlation query ("connection between X and Y")
    topics = _parse_correlation(query)
    corr_results: list[dict] = []
    if topics:
        corr_results = await ctx.correlate(topics[0], topics[1])

    # Contact lookup for people queries
    contacts: list[dict] = []
    if person:
        contacts = await ctx.get_contacts(person)

    # Merge all evidence
    all_sources = results + kg_results + corr_results
    if not all_sources:
        return {"answer": "I couldn't find anything in your memory about that.", "sources": []}

    # Compose answer
    if ctx.has_permission("llm_access"):
        context_text = _format_context(results, kg_results, corr_results, contacts)
        prompt = (
            f"Based on the user's personal memory, answer their question.\n\n"
            f"Memory context:\n{context_text}\n\n"
            f"User's question: {query}\n\n"
            f"Answer naturally, cite sources when relevant. If unsure, say so."
        )
        answer = await ctx.llm_complete(prompt, task_type="reasoning")
        if answer:
            return {
                "answer": answer,
                "sources": [_extract_source(r) for r in results[:5]],
                "contacts": [c.get("name", c.get("email", "")) for c in contacts[:3]],
            }

    # Fallback: manual formatting
    answer_parts = []
    if results:
        answer_parts.append(f"Found {len(results)} memory entries:")
        for r in results[:5]:
            text = r.get("text", "")[:200]
            source = r.get("source", "unknown")
            answer_parts.append(f"  - [{source}] {text}")

    if kg_results:
        answer_parts.append(f"\nKnowledge graph ({len(kg_results)} references):")
        for ref in kg_results[:3]:
            if isinstance(ref, dict):
                answer_parts.append(f"  - {ref.get('summary', ref.get('text', str(ref)))[:200]}")

    return {
        "answer": "\n".join(answer_parts) if answer_parts else "No relevant results found.",
        "sources": [_extract_source(r) for r in results[:5]],
        "contacts": [c.get("name", c.get("email", "")) for c in contacts[:3]],
    }


def _parse_person_topic(query: str) -> tuple[str | None, str | None]:
    """Extract person and topic from queries like 'what did Marco say about pricing'."""
    import re

    m = re.search(
        r"(?:what did|who said|did)\s+(\w+)\s+(?:say|mention|tell|write)\s+(?:about\s+)?(.+)",
        query,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    m = re.search(r"(?:who said|who mentioned)\s+(.+)", query, re.IGNORECASE)
    if m:
        return None, m.group(1).strip()

    return None, None


def _parse_correlation(query: str) -> tuple[str, str] | None:
    """Extract two topics from 'connection between X and Y'."""
    import re

    m = re.search(
        r"(?:connection|correlation|link|relation)\s+between\s+(.+?)\s+and\s+(.+)",
        query,
        re.IGNORECASE,
    )
    if m:
        return (m.group(1).strip(), m.group(2).strip())
    return None


def _extract_source(result: dict) -> dict:
    """Create a minimal source reference from a search result."""
    return {
        "text": result.get("text", "")[:150],
        "source": result.get("source", "unknown"),
        "score": result.get("score", 0),
    }


def _format_context(
    results: list[dict],
    kg_results: list[dict],
    corr_results: list[dict],
    contacts: list[dict],
) -> str:
    """Format all evidence into a text block for LLM context."""
    parts = []

    if results:
        parts.append("## Memory entries")
        for r in results[:8]:
            text = r.get("text", "")[:300]
            source = r.get("source", "unknown")
            parts.append(f"- [{source}] {text}")

    if kg_results:
        parts.append("\n## Knowledge graph")
        for ref in kg_results[:5]:
            if isinstance(ref, dict):
                parts.append(f"- {ref.get('summary', ref.get('text', str(ref)))[:300]}")

    if corr_results:
        parts.append("\n## Correlations")
        for c in corr_results[:3]:
            if isinstance(c, dict):
                parts.append(f"- {c.get('summary', str(c))[:300]}")

    if contacts:
        parts.append("\n## Relevant contacts")
        for c in contacts[:3]:
            name = c.get("name", c.get("email", "unknown"))
            email = c.get("email", "")
            parts.append(f"- {name} ({email})")

    return "\n".join(parts)
