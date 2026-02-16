"""
OmniBrain — Knowledge Graph (Day 22-23)

Multi-source knowledge querying and correlation engine.
Cross-references emails, calendar, contacts, and memory to answer
complex questions like "What did Marco say about pricing?"

Architecture:
    KnowledgeGraph
    ├── query()             — natural language → structured answer
    ├── who_said_what()     — "What did X say about Y?"
    ├── get_contact_graph() — relationship map between contacts
    ├── get_topic_timeline()— chronological topic evolution
    └── correlate()         — cross-source correlation

This is the layer that makes OmniBrain feel intelligent.
It doesn't use an actual graph database — it's a query engine
over SQLite events/contacts + FTS5 memory.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from omnibrain.db import OmniBrainDB
from omnibrain.memory import MemoryDocument, MemoryManager
from omnibrain.models import ContactInfo

logger = logging.getLogger("omnibrain.knowledge_graph")


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SourceReference:
    """A specific reference from a source (email, calendar, note)."""

    source_type: str       # email, calendar, note, memory
    source_id: str
    date: str
    text: str
    contact: str = ""
    relevance_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "date": self.date,
            "text": self.text[:500],
            "contact": self.contact,
            "relevance_score": self.relevance_score,
        }


@dataclass
class KnowledgeAnswer:
    """Answer to a knowledge graph query with supporting references."""

    query: str
    summary: str
    references: list[SourceReference] = field(default_factory=list)
    contacts_involved: list[str] = field(default_factory=list)
    time_span: str = ""
    source_count: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "summary": self.summary,
            "references": [r.to_dict() for r in self.references],
            "contacts_involved": self.contacts_involved,
            "time_span": self.time_span,
            "source_count": self.source_count,
            "total_references": len(self.references),
        }

    @property
    def has_results(self) -> bool:
        return len(self.references) > 0


@dataclass
class ContactRelationship:
    """Relationship between two contacts based on co-occurrence."""

    contact_a: str
    contact_b: str
    shared_events: int = 0
    shared_threads: int = 0
    topics: list[str] = field(default_factory=list)
    last_interaction: str = ""

    @property
    def strength(self) -> float:
        """Relationship strength: 0.0 to 1.0."""
        return min((self.shared_events + self.shared_threads) / 10, 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contact_a": self.contact_a,
            "contact_b": self.contact_b,
            "shared_events": self.shared_events,
            "shared_threads": self.shared_threads,
            "topics": self.topics[:10],
            "strength": self.strength,
            "last_interaction": self.last_interaction,
        }


@dataclass
class TopicEntry:
    """A single point on a topic's timeline."""

    date: str
    source_type: str
    contact: str
    text: str
    source_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "source_type": self.source_type,
            "contact": self.contact,
            "text": self.text[:300],
            "source_id": self.source_id,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Knowledge Graph
# ═══════════════════════════════════════════════════════════════════════════


class KnowledgeGraph:
    """Multi-source knowledge query engine.

    Answers complex questions by cross-referencing events, contacts,
    and memory documents. This is what makes OmniBrain feel smart.

    Usage:
        kg = KnowledgeGraph(db, memory)
        answer = kg.query("What did Marco say about pricing?")
        print(answer.summary)
        for ref in answer.references:
            print(f"  [{ref.source_type}] {ref.date}: {ref.text}")
    """

    def __init__(self, db: OmniBrainDB, memory: MemoryManager):
        self._db = db
        self._memory = memory

    # ── Main Query Interface ──

    def query(
        self,
        question: str,
        max_results: int = 20,
        days: int = 90,
    ) -> KnowledgeAnswer:
        """Answer a natural language question by searching all sources.

        Detects question type and routes to specialized handler:
        - "What did X say about Y?" → who_said_what
        - "timeline of X" → get_topic_timeline
        - Default → correlate across all sources
        """
        q_lower = question.lower()

        # Detect "What did X say about Y?" pattern
        who_match = _parse_who_said_what(q_lower)
        if who_match:
            person, topic = who_match
            return self.who_said_what(person, topic, max_results=max_results, days=days)

        # Detect timeline queries
        if any(kw in q_lower for kw in ("timeline", "history of", "evolution of", "progress of")):
            topic = _extract_topic(question)
            if topic:
                timeline = self.get_topic_timeline(topic, days=days)
                return _timeline_to_answer(question, timeline)

        # Default: correlate across sources
        return self.correlate(question, max_results=max_results, days=days)

    # ── Who Said What ──

    def who_said_what(
        self,
        person: str,
        topic: str,
        max_results: int = 20,
        days: int = 90,
    ) -> KnowledgeAnswer:
        """Find what a specific person said about a topic.

        Searches:
        1. Memory docs mentioning the person + topic
        2. Events from email/calendar involving the person
        3. Contacts DB for the person's details
        """
        references: list[SourceReference] = []

        # 1. Search memory for person + topic
        combined_query = f"{person} {topic}"
        memory_results = self._memory.search(
            combined_query, max_results=max_results, time_range_days=days,
        )

        for doc in memory_results:
            # Filter: must mention person
            if not _mentions_person(doc.text, person) and not _mentions_person(doc.source, person):
                continue
            references.append(SourceReference(
                source_type=doc.source_type or "memory",
                source_id=doc.id,
                date=doc.timestamp,
                text=doc.text,
                contact=_extract_contact_from_doc(doc, person),
                relevance_score=doc.score,
            ))

        # 2. Search events for this person + topic
        event_refs = self._search_events_for_person(person, topic, days=days)
        references.extend(event_refs)

        # Deduplicate by source_id
        seen_ids: set[str] = set()
        unique_refs: list[SourceReference] = []
        for ref in references:
            if ref.source_id not in seen_ids:
                seen_ids.add(ref.source_id)
                unique_refs.append(ref)
        references = unique_refs

        # Sort by date descending
        references.sort(key=lambda r: r.date, reverse=True)
        references = references[:max_results]

        # Build summary
        contact_info = self._resolve_contact(person)
        contact_name = contact_info.name if contact_info else person

        source_count = _count_sources(references)
        dates = [r.date for r in references if r.date]
        time_span = _compute_time_span(dates) if dates else ""

        summary = (
            f"Found {len(references)} reference(s) from {contact_name} "
            f"about '{topic}'"
        )
        if source_count:
            parts = [f"{count} {stype}" for stype, count in source_count.items()]
            summary += f" across {', '.join(parts)}"
        if time_span:
            summary += f" spanning {time_span}"

        return KnowledgeAnswer(
            query=f"What did {person} say about {topic}?",
            summary=summary,
            references=references,
            contacts_involved=[contact_name],
            time_span=time_span,
            source_count=source_count,
        )

    # ── Cross-Source Correlation ──

    def correlate(
        self,
        query: str,
        max_results: int = 20,
        days: int = 90,
    ) -> KnowledgeAnswer:
        """Search across all sources and correlate results.

        Combines memory search + event search + contact lookup.
        """
        references: list[SourceReference] = []

        # 1. Memory search
        memory_results = self._memory.search(query, max_results=max_results, time_range_days=days)
        for doc in memory_results:
            references.append(SourceReference(
                source_type=doc.source_type or "memory",
                source_id=doc.id,
                date=doc.timestamp,
                text=doc.text,
                contact=doc.source,
                relevance_score=doc.score,
            ))

        # 2. Event search (DB FTS)
        try:
            events = self._db.search_events(query, limit=max_results)
            for ev in events:
                source_id = f"event_{ev.get('id', '')}"
                if source_id not in {r.source_id for r in references}:
                    references.append(SourceReference(
                        source_type=ev.get("source", "event"),
                        source_id=source_id,
                        date=ev.get("timestamp", ""),
                        text=ev.get("title", "") + "\n" + ev.get("content", ""),
                        contact=ev.get("source", ""),
                    ))
        except Exception as e:
            logger.debug(f"Event search failed: {e}")

        # Sort by relevance
        references.sort(key=lambda r: r.relevance_score, reverse=True)
        references = references[:max_results]

        # Extract contacts
        contacts = list({r.contact for r in references if r.contact})
        source_count = _count_sources(references)
        dates = [r.date for r in references if r.date]
        time_span = _compute_time_span(dates) if dates else ""

        summary = f"Found {len(references)} result(s) for '{query}'"
        if source_count:
            parts = [f"{count} {stype}" for stype, count in source_count.items()]
            summary += f" across {', '.join(parts)}"

        return KnowledgeAnswer(
            query=query,
            summary=summary,
            references=references,
            contacts_involved=contacts,
            time_span=time_span,
            source_count=source_count,
        )

    # ── Contact Relationship Graph ──

    def get_contact_graph(
        self,
        contact_email: str | None = None,
        min_strength: float = 0.1,
        days: int = 90,
    ) -> list[ContactRelationship]:
        """Get relationships between contacts based on co-occurrence.

        If contact_email is provided, shows relationships for that contact.
        Otherwise, shows the strongest relationships across all contacts.
        """
        # Get all contacts
        contacts = self._db.get_contacts(limit=200)
        if not contacts:
            return []

        # Get recent events with contact info
        since = datetime.now() - timedelta(days=days)
        events = self._db.get_events(since=since, limit=500)

        # Build co-occurrence matrix
        relationships: dict[tuple[str, str], ContactRelationship] = {}

        for ev in events:
            metadata = _parse_metadata(ev.get("metadata", "{}"))
            attendees = _extract_attendees(metadata, ev)

            # Count pairwise co-occurrences
            for i, a in enumerate(attendees):
                for b in attendees[i + 1:]:
                    key = (min(a, b), max(a, b))
                    if key not in relationships:
                        relationships[key] = ContactRelationship(
                            contact_a=key[0],
                            contact_b=key[1],
                        )
                    rel = relationships[key]

                    source = ev.get("source", "")
                    if source == "calendar":
                        rel.shared_events += 1
                    else:
                        rel.shared_threads += 1

                    # Extract topic from title
                    title = ev.get("title", "")
                    if title and title not in rel.topics:
                        rel.topics.append(title)

                    ts = ev.get("timestamp", "")
                    if ts > rel.last_interaction:
                        rel.last_interaction = ts

        # Filter
        result = [r for r in relationships.values() if r.strength >= min_strength]

        if contact_email:
            result = [
                r for r in result
                if contact_email in (r.contact_a, r.contact_b)
            ]

        result.sort(key=lambda r: r.strength, reverse=True)
        return result

    # ── Topic Timeline ──

    def get_topic_timeline(
        self,
        topic: str,
        days: int = 90,
        max_entries: int = 50,
    ) -> list[TopicEntry]:
        """Build a chronological timeline for a topic across all sources."""
        entries: list[TopicEntry] = []

        # Memory documents
        docs = self._memory.search(topic, max_results=max_entries, time_range_days=days)
        for doc in docs:
            entries.append(TopicEntry(
                date=doc.timestamp,
                source_type=doc.source_type or "memory",
                contact=doc.source,
                text=doc.text,
                source_id=doc.id,
            ))

        # Events
        try:
            events = self._db.search_events(topic, limit=max_entries)
            for ev in events:
                entries.append(TopicEntry(
                    date=ev.get("timestamp", ""),
                    source_type=ev.get("source", "event"),
                    contact=ev.get("source", ""),
                    text=ev.get("title", "") + "\n" + ev.get("content", ""),
                    source_id=f"event_{ev.get('id', '')}",
                ))
        except Exception as e:
            logger.debug(f"Event timeline search failed: {e}")

        # Sort chronologically
        entries.sort(key=lambda e: e.date)
        return entries[:max_entries]

    # ── Contact Enrichment ──

    def get_contact_summary(self, identifier: str) -> dict[str, Any]:
        """Get a comprehensive summary for a contact.

        Searches by email or name. Returns contact info + recent interactions.
        """
        contact = self._resolve_contact(identifier)
        if not contact:
            return {"found": False, "identifier": identifier}

        # Fetch recent interactions from memory
        recent = self._memory.search(
            contact.email or contact.name,
            max_results=10,
            time_range_days=90,
        )

        # Count by source type
        source_breakdown: dict[str, int] = defaultdict(int)
        for doc in recent:
            source_breakdown[doc.source_type or "unknown"] += 1

        # Get relationships
        relationships = self.get_contact_graph(contact_email=contact.email, days=90)

        return {
            "found": True,
            "contact": contact.to_dict(),
            "is_vip": contact.is_vip,
            "recent_interactions": len(recent),
            "source_breakdown": dict(source_breakdown),
            "relationships": [r.to_dict() for r in relationships[:5]],
            "last_topics": [doc.text[:100] for doc in recent[:5]],
        }

    # ── Internal Helpers ──

    def _resolve_contact(self, identifier: str) -> ContactInfo | None:
        """Resolve a contact by email or name.

        Tries exact email match first, then name search.
        """
        # Try email
        if "@" in identifier:
            return self._db.get_contact(identifier)

        # Try name search across all contacts
        contacts = self._db.get_contacts(limit=200)
        identifier_lower = identifier.lower()
        for c in contacts:
            if identifier_lower in c.name.lower() or identifier_lower in c.email.lower():
                return c
        return None

    def _search_events_for_person(
        self,
        person: str,
        topic: str,
        days: int = 90,
    ) -> list[SourceReference]:
        """Search events mentioning a person and topic."""
        refs: list[SourceReference] = []

        try:
            # Search events for the topic
            events = self._db.search_events(topic, limit=50)
            for ev in events:
                content = (ev.get("title", "") + " " + ev.get("content", "")).lower()
                metadata_str = ev.get("metadata", "{}")
                metadata = _parse_metadata(metadata_str)

                # Check if person is mentioned in content or metadata
                person_lower = person.lower()
                in_content = person_lower in content
                in_metadata = person_lower in json.dumps(metadata).lower()
                in_source = person_lower in ev.get("source", "").lower()

                if in_content or in_metadata or in_source:
                    refs.append(SourceReference(
                        source_type=ev.get("source", "event"),
                        source_id=f"event_{ev.get('id', '')}",
                        date=ev.get("timestamp", ""),
                        text=ev.get("title", "") + "\n" + ev.get("content", ""),
                        contact=person,
                    ))
        except Exception as e:
            logger.debug(f"Event search for person failed: {e}")

        return refs


# ═══════════════════════════════════════════════════════════════════════════
# Internal Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _parse_who_said_what(question: str) -> tuple[str, str] | None:
    """Parse "What did X say about Y?" variants.

    Handles:
        "what did marco say about pricing?"
        "what has marco said about the proposal?"
        "cosa ha detto marco sul pricing?"
        "marco's thoughts on pricing"
    """
    patterns = [
        r"what (?:did|has|does) (\w+) (?:say|said|mention|tell|write|wrote) about (.+?)[\?]?$",
        r"cosa ha detto (\w+) (?:su|sul|sulla|sullo|riguardo) (.+?)[\?]?$",
        r"(\w+)'s (?:thoughts|views|opinion|position|comments?) on (.+?)[\?]?$",
        r"what (?:did|has) (\w+) (?:say|said) (?:about|regarding|on) (.+?)[\?]?$",
    ]
    for pat in patterns:
        m = re.search(pat, question, re.IGNORECASE)
        if m:
            person = m.group(1).strip()
            topic = m.group(2).strip()
            if person and topic:
                return (person, topic)
    return None


def _extract_topic(question: str) -> str:
    """Extract the topic from a timeline/history query."""
    patterns = [
        r"(?:timeline|history|evolution|progress) (?:of|for) (.+?)[\?]?$",
        r"(.+?) (?:timeline|history)[\?]?$",
    ]
    for pat in patterns:
        m = re.search(pat, question, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    # Fallback: use the whole question minus common words
    stop_words = {"the", "a", "an", "of", "for", "about", "show", "me", "what", "is"}
    words = [w for w in question.split() if w.lower() not in stop_words]
    return " ".join(words) if words else question


def _mentions_person(text: str, person: str) -> bool:
    """Check if text mentions a person (case-insensitive word match)."""
    return person.lower() in text.lower()


def _extract_contact_from_doc(doc: MemoryDocument, person: str) -> str:
    """Extract the best contact identifier from a memory document."""
    # If any contact in the doc matches the person
    person_lower = person.lower()
    for contact in doc.contacts:
        if person_lower in contact.lower():
            return contact
    # Fall back to source if it mentions the person
    if _mentions_person(doc.source, person):
        return doc.source
    return person


def _count_sources(references: list[SourceReference]) -> dict[str, int]:
    """Count references by source type."""
    counts: dict[str, int] = defaultdict(int)
    for ref in references:
        counts[ref.source_type] += 1
    return dict(counts)


def _compute_time_span(dates: list[str]) -> str:
    """Compute a human-readable time span from date strings."""
    parsed = []
    for d in dates:
        try:
            parsed.append(datetime.fromisoformat(d))
        except (ValueError, TypeError):
            pass

    if len(parsed) < 2:
        return ""

    earliest = min(parsed)
    latest = max(parsed)
    delta = latest - earliest

    if delta.days == 0:
        return "same day"
    elif delta.days == 1:
        return "1 day"
    elif delta.days < 7:
        return f"{delta.days} days"
    elif delta.days < 30:
        weeks = delta.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''}"
    else:
        months = delta.days // 30
        return f"{months} month{'s' if months > 1 else ''}"


def _parse_metadata(raw: str | dict) -> dict[str, Any]:
    """Safely parse metadata JSON."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_attendees(metadata: dict[str, Any], event: dict[str, Any]) -> list[str]:
    """Extract attendee identifiers from event metadata."""
    attendees = []

    # From metadata
    raw = metadata.get("attendees", [])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = []
    if isinstance(raw, list):
        attendees.extend(raw)

    # From event source as fallback
    source = event.get("source", "")
    if source and "@" in source and source not in attendees:
        attendees.append(source)

    return attendees


def _timeline_to_answer(question: str, timeline: list[TopicEntry]) -> KnowledgeAnswer:
    """Convert a timeline to a KnowledgeAnswer."""
    references = [
        SourceReference(
            source_type=entry.source_type,
            source_id=entry.source_id,
            date=entry.date,
            text=entry.text,
            contact=entry.contact,
        )
        for entry in timeline
    ]

    contacts = list({e.contact for e in timeline if e.contact})
    source_count = _count_sources(references)
    dates = [e.date for e in timeline if e.date]
    time_span = _compute_time_span(dates) if dates else ""

    summary = f"Timeline with {len(timeline)} entries"
    if time_span:
        summary += f" spanning {time_span}"

    return KnowledgeAnswer(
        query=question,
        summary=summary,
        references=references,
        contacts_involved=contacts,
        time_span=time_span,
        source_count=source_count,
    )
