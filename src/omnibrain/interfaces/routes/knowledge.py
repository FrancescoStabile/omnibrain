"""Knowledge graph routes for OmniBrain API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, Query

logger = logging.getLogger("omnibrain.api")


def _contact_to_dict(c: Any) -> dict[str, Any]:
    """Normalize a ContactInfo object OR dict to a plain dict."""
    if isinstance(c, dict):
        return c
    # ContactInfo dataclass
    return {
        "email": getattr(c, "email", ""),
        "name": getattr(c, "name", ""),
        "relationship": getattr(c, "relationship", ""),
        "organization": getattr(c, "organization", ""),
        "interaction_count": getattr(c, "interaction_count", 0),
        "last_interaction": (
            c.last_interaction.isoformat()
            if getattr(c, "last_interaction", None)
            else ""
        ),
    }


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

    # ── GET /api/v1/knowledge/entities ──

    @app.get("/api/v1/knowledge/entities")
    async def list_entities(
        type: str = Query("", description="Filter: person, company, topic, project"),
        sort: str = Query("frequency", description="Sort: frequency, recent, connections"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List known entities (contacts, topics, companies) with relationship counts."""
        db = server._db
        try:
            # Pull contacts as person-type entities
            contacts = db.get_contacts(limit=limit)
            entities: list[dict[str, Any]] = []
            for _c in contacts:
                c = _contact_to_dict(_c)
                entity_type = "person"
                if type and entity_type != type:
                    continue
                entities.append({
                    "id": c.get("email", ""),
                    "name": c.get("name") or c.get("email", ""),
                    "type": entity_type,
                    "email": c.get("email", ""),
                    "organization": c.get("organization", ""),
                    "interaction_count": c.get("interaction_count", 0),
                    "last_seen": c.get("last_interaction", "") or c.get("last_seen", ""),
                    "relationship": c.get("relationship", ""),
                })

            # Also harvest topic-type entities from observations
            try:
                observations = db.get_observations(days=90)
                seen_topics: set[str] = set()
                for obs in observations:
                    desc = obs.get("description", "")
                    pattern_type = obs.get("pattern_type", "")
                    if desc and (not type or type == "topic"):
                        topic_key = desc[:60]
                        if topic_key not in seen_topics:
                            seen_topics.add(topic_key)
                            entities.append({
                                "id": f"topic:{topic_key}",
                                "name": desc[:80],
                                "type": "topic",
                                "email": "",
                                "organization": "",
                                "interaction_count": obs.get("occurrences", 1),
                                "last_seen": obs.get("timestamp", ""),
                                "relationship": pattern_type,
                            })
            except Exception:
                pass  # observations are optional

            # Sort
            if sort == "recent":
                entities.sort(key=lambda e: e.get("last_seen") or "", reverse=True)
            elif sort == "connections":
                entities.sort(key=lambda e: e.get("interaction_count", 0), reverse=True)
            else:  # frequency (default)
                entities.sort(key=lambda e: e.get("interaction_count", 0), reverse=True)

            total = len(entities)
            entities = entities[offset : offset + limit]
            return {"entities": entities, "total": total, "offset": offset, "limit": limit}
        except Exception as e:
            logger.warning("Entity listing failed: %s", e)
            return {"entities": [], "total": 0, "offset": offset, "limit": limit, "error": str(e)}

    # ── GET /api/v1/knowledge/graph ──

    @app.get("/api/v1/knowledge/graph")
    async def knowledge_graph_data(
        limit: int = Query(100, ge=1, le=500),
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Return graph nodes + edges for force-graph visualization."""
        db = server._db
        try:
            contacts = db.get_contacts(limit=limit)
            nodes: list[dict[str, Any]] = []
            edges: list[dict[str, Any]] = []
            contact_emails: set[str] = set()

            for _c in contacts:
                c = _contact_to_dict(_c)
                email = c.get("email", "")
                if not email:
                    continue
                contact_emails.add(email)
                nodes.append({
                    "id": email,
                    "label": c.get("name") or email,
                    "type": "person",
                    "val": max(1, c.get("interaction_count", 1)),
                    "organization": c.get("organization", ""),
                    "relationship": c.get("relationship", ""),
                })

            # Build edges from shared events (emails/meetings involving multiple contacts)
            try:
                events = db.get_events(limit=200)
                for event in events:
                    meta_str = event.get("metadata") or "{}"
                    try:
                        import json
                        meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
                    except Exception:
                        meta = {}

                    # attendees from calendar events
                    attendees = meta.get("attendees", [])
                    if isinstance(attendees, list) and len(attendees) >= 2:
                        for i in range(len(attendees)):
                            for j in range(i + 1, len(attendees)):
                                a = attendees[i]
                                b = attendees[j]
                                if isinstance(a, dict):
                                    a = a.get("email", str(a))
                                if isinstance(b, dict):
                                    b = b.get("email", str(b))
                                if a in contact_emails and b in contact_emails:
                                    edges.append({
                                        "source": a,
                                        "target": b,
                                        "type": "shared_meeting",
                                    })
            except Exception:
                pass

            # Add topic nodes from observations and link to contacts that mention them
            try:
                observations = db.get_observations(days=30)
                for obs in observations[:30]:  # limit topic nodes
                    topic = obs.get("description", "")[:40]
                    related = obs.get("related_contact") or obs.get("contact")
                    if topic:
                        topic_id = f"topic:{topic}"
                        if not any(n["id"] == topic_id for n in nodes):
                            nodes.append({
                                "id": topic_id,
                                "label": topic,
                                "type": "topic",
                                "val": 0.5,
                            })
                        if related and related in contact_emails:
                            edges.append({
                                "source": related,
                                "target": topic_id,
                                "type": "discussed",
                            })
            except Exception:
                pass

            return {
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
            }
        except Exception as e:
            logger.warning("Graph data failed: %s", e)
            return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0, "error": str(e)}

            logger.warning("Contact summary failed: %s", e)
            return {"error": str(e)}
