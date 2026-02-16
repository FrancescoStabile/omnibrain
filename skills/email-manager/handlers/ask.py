"""Email Manager — Ask handler.

Called when the user asks about emails, inbox, contacts, etc.
Searches memory and (if wired) uses LLM to compose a response.
"""

from __future__ import annotations


async def handle(ctx, query: str) -> dict:
    """Answer questions about emails using memory and knowledge graph.

    Returns ``{"answer": str, "sources": list[dict]}``.
    """
    # 1. Search memory for email-related content
    results = await ctx.memory_search(query, limit=10, source="skill:email-manager")

    # Fallback: broaden search to all sources
    if not results:
        results = await ctx.memory_search(query, limit=10)

    if not results:
        return {"answer": "I don't have any email-related information matching your query.", "sources": []}

    # 2. Extract unique senders mentioned in query
    contacts = await ctx.get_contacts(query)

    # 3. Build context for LLM (or format directly)
    source_texts = []
    for r in results[:5]:
        source_texts.append(r.get("text", "")[:300])

    # If LLM is available, compose a natural answer
    if ctx.has_permission("llm_access"):
        context_block = "\n---\n".join(source_texts)
        prompt = (
            f"Based on these emails from the user's inbox, answer: {query}\n\n"
            f"Context:\n{context_block}\n\n"
            "Be concise and helpful. Reference specific emails/senders."
        )
        try:
            answer = await ctx.llm_complete(prompt, task_type="quick")
            if answer:
                return {
                    "answer": answer,
                    "sources": results[:5],
                    "contacts": [c.get("name", c.get("email", "")) for c in contacts[:3]],
                }
        except Exception:
            pass  # Fall through to manual formatting

    # 4. Manual formatting fallback
    lines = [f"Found {len(results)} email(s) related to your query:"]
    for r in results[:5]:
        text = r.get("text", "")[:150]
        source = r.get("source", "")
        lines.append(f"  • {text}  [{source}]")

    return {
        "answer": "\n".join(lines),
        "sources": results[:5],
    }
