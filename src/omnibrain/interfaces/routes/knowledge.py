"""Knowledge graph routes for OmniBrain API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, Query

logger = logging.getLogger("omnibrain.api")


def register_knowledge_routes(app, server, verify_api_key) -> None:  # noqa: ANN001
    """Register knowledge graph routes."""

    @app.get("/api/v1/knowledge/query")
    async def knowledge_query(
        q: str = "",
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Query the knowledge graph with natural language."""
        kg = getattr(server, "_knowledge_graph", None)
        if not kg:
            return {"summary": "", "references": [], "error": "Knowledge graph not available"}
        if not q.strip():
            return {"summary": "", "references": [], "error": "Empty query"}
        try:
            result = kg.query(q.strip())
            # Map backend SourceReference fields → frontend KnowledgeReference
            refs = [
                {
                    "text": s.text[:500],
                    "source": s.source_type or s.contact or "memory",
                    "date": s.date,
                    "score": s.relevance_score,
                }
                for s in result.references[:10]
            ]
            total_sources = sum(result.source_count.values()) if result.source_count else 0
            return {
                "summary": result.summary,
                "references": refs,
                "source_count": total_sources,
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
        kg = getattr(server, "_knowledge_graph", None)
        if not kg:
            return {"error": "Knowledge graph not available"}
        try:
            return kg.get_contact_summary(identifier)
        except Exception as e:
            logger.warning("Contact summary failed: %s", e)
            return {"error": str(e)}
