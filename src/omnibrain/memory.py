"""
OmniBrain — Memory System

Dual-backend semantic memory: SQLite FTS5 (always) + ChromaDB (optional).

Architecture:
    MemoryStore (abstract)
    ├── SQLiteMemoryStore — FTS5-based search (always available)
    └── ChromaMemoryStore — Vector-based semantic search (optional)

    MemoryManager — Facade over both backends.
    - store(text, metadata) → stores in both backends
    - search(query, ...) → queries best available backend
    - Falls back gracefully if ChromaDB isn't available

Follows manifesto Section 14 (Storage & Memory Architecture):
    Event arrives → 1. Store in SQLite → 2. Embed in ChromaDB → 3. Extract entities
"""

from __future__ import annotations

import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger("omnibrain.memory")


# ═══════════════════════════════════════════════════════════════════════════
# Memory Document
# ═══════════════════════════════════════════════════════════════════════════


class MemoryDocument:
    """A document stored in the memory system."""

    def __init__(
        self,
        id: str,
        text: str,
        source: str = "",
        source_type: str = "",
        timestamp: str = "",
        contacts: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        score: float = 0.0,
    ):
        self.id = id
        self.text = text
        self.source = source
        self.source_type = source_type
        self.timestamp = timestamp or datetime.now().isoformat()
        self.contacts = contacts or []
        self.metadata = metadata or {}
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "source_type": self.source_type,
            "timestamp": self.timestamp,
            "contacts": self.contacts,
            "metadata": self.metadata,
            "score": self.score,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Abstract MemoryStore
# ═══════════════════════════════════════════════════════════════════════════


class MemoryStore(ABC):
    """Abstract memory store interface."""

    @abstractmethod
    def store(self, doc: MemoryDocument) -> bool:
        """Store a document. Returns True if stored successfully."""
        ...

    @abstractmethod
    def search(
        self,
        query: str,
        max_results: int = 10,
        source_filter: str = "all",
        time_range_days: int = 90,
    ) -> list[MemoryDocument]:
        """Search for relevant documents."""
        ...

    @abstractmethod
    def delete(self, doc_id: str) -> bool:
        """Delete a document by ID."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return total document count."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# SQLite FTS5 Memory Store (always available)
# ═══════════════════════════════════════════════════════════════════════════

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    source TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    timestamp TEXT DEFAULT (datetime('now')),
    contacts TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}'
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    text,
    source,
    source_type,
    content='memory',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
    INSERT INTO memory_fts(rowid, text, source, source_type)
    VALUES (new.rowid, new.text, new.source, new.source_type);
END;

CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, text, source, source_type)
    VALUES ('delete', old.rowid, old.text, old.source, old.source_type);
END;
"""


class SQLiteMemoryStore(MemoryStore):
    """SQLite FTS5-based memory store.

    Always available. Uses FTS5 full-text search with BM25 ranking.
    Good enough for keyword-based queries; ChromaDB adds semantic search.
    """

    def __init__(self, data_dir: Path):
        self._db_path = data_dir / "memory.db"
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the memory database."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(MEMORY_SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def store(self, doc: MemoryDocument) -> bool:
        """Store a document. Handles FTS5 sync manually for REPLACE."""
        try:
            with self._conn() as conn:
                # Delete existing first (to keep FTS5 in sync via trigger)
                conn.execute("DELETE FROM memory WHERE id = ?", (doc.id,))
                conn.execute(
                    """INSERT INTO memory
                       (id, text, source, source_type, timestamp, contacts, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        doc.id,
                        doc.text,
                        doc.source,
                        doc.source_type,
                        doc.timestamp,
                        json.dumps(doc.contacts),
                        json.dumps(doc.metadata),
                    ),
                )
            return True
        except Exception as e:
            logger.warning(f"Failed to store memory document {doc.id}: {e}")
            return False

    def search(
        self,
        query: str,
        max_results: int = 10,
        source_filter: str = "all",
        time_range_days: int = 90,
    ) -> list[MemoryDocument]:
        """Search using FTS5 with BM25 ranking."""
        try:
            # Sanitize query for FTS5 — escape special characters
            fts_query = _sanitize_fts_query(query)
            if not fts_query:
                return []

            cutoff = (datetime.now() - timedelta(days=time_range_days)).isoformat()

            with self._conn() as conn:
                if source_filter and source_filter != "all":
                    rows = conn.execute(
                        """SELECT m.*, rank
                           FROM memory m
                           JOIN memory_fts ON memory_fts.rowid = m.rowid
                           WHERE memory_fts MATCH ?
                             AND m.source_type = ?
                             AND m.timestamp >= ?
                           ORDER BY rank
                           LIMIT ?""",
                        (fts_query, source_filter, cutoff, max_results),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT m.*, rank
                           FROM memory m
                           JOIN memory_fts ON memory_fts.rowid = m.rowid
                           WHERE memory_fts MATCH ?
                             AND m.timestamp >= ?
                           ORDER BY rank
                           LIMIT ?""",
                        (fts_query, cutoff, max_results),
                    ).fetchall()

            return [_row_to_doc(row) for row in rows]

        except Exception as e:
            logger.error(f"Memory search failed for '{query}': {e}")
            return []

    def delete(self, doc_id: str) -> bool:
        try:
            with self._conn() as conn:
                conn.execute("DELETE FROM memory WHERE id = ?", (doc_id,))
            return True
        except Exception as e:
            logger.warning(f"Failed to delete memory doc {doc_id}: {e}")
            return False

    def count(self) -> int:
        try:
            with self._conn() as conn:
                row = conn.execute("SELECT COUNT(*) FROM memory").fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def get_by_id(self, doc_id: str) -> MemoryDocument | None:
        """Retrieve a single document by ID."""
        try:
            with self._conn() as conn:
                row = conn.execute("SELECT * FROM memory WHERE id = ?", (doc_id,)).fetchone()
                if row:
                    return _row_to_doc(row)
        except Exception as e:
            logger.warning(f"Failed to get memory doc {doc_id}: {e}")
        return None

    def get_recent(self, max_results: int = 20, source_filter: str = "all") -> list[MemoryDocument]:
        """Get most recent documents."""
        try:
            with self._conn() as conn:
                if source_filter and source_filter != "all":
                    rows = conn.execute(
                        "SELECT * FROM memory WHERE source_type = ? ORDER BY timestamp DESC LIMIT ?",
                        (source_filter, max_results),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM memory ORDER BY timestamp DESC LIMIT ?",
                        (max_results,),
                    ).fetchall()
            return [_row_to_doc(row) for row in rows]
        except Exception as e:
            logger.error(f"get_recent failed: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════
# ChromaDB Memory Store (optional)
# ═══════════════════════════════════════════════════════════════════════════


def _chromadb_available() -> bool:
    """Check if ChromaDB is importable and functional."""
    try:
        import chromadb
        return True
    except Exception:
        return False


class ChromaMemoryStore(MemoryStore):
    """ChromaDB vector-based semantic memory store.

    Optional — only used when chromadb is installed and working.
    Falls back to SQLiteMemoryStore if not available.
    """

    def __init__(self, data_dir: Path, collection_name: str = "omnibrain_memory"):
        self._data_dir = data_dir / "chroma"
        self._collection_name = collection_name
        self._client = None
        self._collection = None
        self._init_chroma()

    def _init_chroma(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            import chromadb
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._data_dir))
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"ChromaDB initialized at {self._data_dir}")
        except Exception as e:
            logger.warning(f"ChromaDB initialization failed: {e}")
            self._client = None
            self._collection = None

    @property
    def is_available(self) -> bool:
        return self._collection is not None

    def store(self, doc: MemoryDocument) -> bool:
        if not self.is_available:
            return False
        try:
            self._collection.upsert(
                ids=[doc.id],
                documents=[doc.text],
                metadatas=[{
                    "source": doc.source,
                    "source_type": doc.source_type,
                    "timestamp": doc.timestamp,
                    "contacts": json.dumps(doc.contacts),
                }],
            )
            return True
        except Exception as e:
            logger.warning(f"ChromaDB store failed for {doc.id}: {e}")
            return False

    def search(
        self,
        query: str,
        max_results: int = 10,
        source_filter: str = "all",
        time_range_days: int = 90,
    ) -> list[MemoryDocument]:
        if not self.is_available:
            return []
        try:
            where = {}
            if source_filter and source_filter != "all":
                where["source_type"] = source_filter

            results = self._collection.query(
                query_texts=[query],
                n_results=max_results,
                where=where if where else None,
            )

            docs = []
            if results and results["documents"]:
                for i, text in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results.get("distances") else 0.0
                    score = 1.0 - distance  # Convert distance to similarity
                    contacts = json.loads(meta.get("contacts", "[]"))
                    docs.append(MemoryDocument(
                        id=results["ids"][0][i],
                        text=text,
                        source=meta.get("source", ""),
                        source_type=meta.get("source_type", ""),
                        timestamp=meta.get("timestamp", ""),
                        contacts=contacts,
                        score=score,
                    ))
            return docs
        except Exception as e:
            logger.error(f"ChromaDB search failed: {e}")
            return []

    def delete(self, doc_id: str) -> bool:
        if not self.is_available:
            return False
        try:
            self._collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            logger.warning(f"ChromaDB delete failed: {e}")
            return False

    def count(self) -> int:
        if not self.is_available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0


# ═══════════════════════════════════════════════════════════════════════════
# Memory Manager (Facade)
# ═══════════════════════════════════════════════════════════════════════════


class MemoryManager:
    """Facade over SQLite + ChromaDB memory stores.

    Always uses SQLite FTS5.
    Optionally uses ChromaDB for better semantic search.
    Exposes a simple API for the rest of OmniBrain.

    Usage:
        memory = MemoryManager(data_dir)
        memory.store("Meeting with Marco about pricing.", source="calendar", source_type="calendar")
        results = memory.search("what did Marco say about pricing?")
    """

    def __init__(self, data_dir: Path, enable_chroma: bool = True):
        self._data_dir = data_dir
        self._sqlite = SQLiteMemoryStore(data_dir)
        self._chroma: ChromaMemoryStore | None = None

        if enable_chroma and _chromadb_available():
            try:
                self._chroma = ChromaMemoryStore(data_dir)
                if not self._chroma.is_available:
                    self._chroma = None
            except Exception as e:
                logger.warning(f"ChromaDB disabled: {e}")
                self._chroma = None

        backend = "SQLite + ChromaDB" if self._chroma else "SQLite only"
        logger.info(f"MemoryManager initialized: {backend}")

    @property
    def has_chroma(self) -> bool:
        return self._chroma is not None and self._chroma.is_available

    def store(
        self,
        text: str,
        id: str = "",
        source: str = "",
        source_type: str = "",
        contacts: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a document in memory. Returns the document ID.

        Stores in both SQLite (always) and ChromaDB (if available).
        """
        doc_id = id or _generate_id(text, source)
        doc = MemoryDocument(
            id=doc_id,
            text=text,
            source=source,
            source_type=source_type,
            contacts=contacts,
            metadata=metadata,
        )

        # Always store in SQLite
        self._sqlite.store(doc)

        # Store in ChromaDB if available
        if self._chroma:
            self._chroma.store(doc)

        return doc_id

    def search(
        self,
        query: str,
        max_results: int = 10,
        source_filter: str = "all",
        time_range_days: int = 90,
    ) -> list[MemoryDocument]:
        """Search memory. Uses ChromaDB if available, falls back to SQLite FTS5."""
        if self._chroma:
            results = self._chroma.search(query, max_results, source_filter, time_range_days)
            if results:
                return results

        # Fallback to FTS5
        return self._sqlite.search(query, max_results, source_filter, time_range_days)

    def get_by_id(self, doc_id: str) -> MemoryDocument | None:
        """Get a specific document by ID."""
        return self._sqlite.get_by_id(doc_id)

    def get_recent(self, max_results: int = 20, source_filter: str = "all") -> list[MemoryDocument]:
        """Get most recent documents."""
        return self._sqlite.get_recent(max_results, source_filter)

    def delete(self, doc_id: str) -> bool:
        """Delete from both stores."""
        ok = self._sqlite.delete(doc_id)
        if self._chroma:
            self._chroma.delete(doc_id)
        return ok

    def count(self) -> int:
        """Return document count (from SQLite, the authoritative store)."""
        return self._sqlite.count()

    def store_email(self, email_data: dict[str, Any]) -> str:
        """Store an email in memory with proper metadata.

        Args:
            email_data: Dict from email_tools' _email_to_agent_view output.

        Returns:
            Document ID.
        """
        subject = email_data.get("subject", "")
        body = email_data.get("body_preview", "")
        sender = email_data.get("sender", "")
        sender_email = email_data.get("sender_email", "")

        text = f"Email from {sender}: {subject}\n\n{body}"
        contacts = [sender_email] if sender_email else []

        return self.store(
            text=text,
            id=f"email_{email_data.get('id', '')}",
            source=sender,
            source_type="email",
            contacts=contacts,
            metadata={
                "email_id": email_data.get("id", ""),
                "thread_id": email_data.get("thread_id", ""),
                "date": email_data.get("date", ""),
                "is_read": email_data.get("is_read", True),
            },
        )

    def store_calendar_event(self, event_data: dict[str, Any]) -> str:
        """Store a calendar event in memory.

        Args:
            event_data: Dict from calendar_tools' _event_to_agent_view output.

        Returns:
            Document ID.
        """
        title = event_data.get("title", "")
        description = event_data.get("description", "")
        attendees = event_data.get("attendees", [])
        location = event_data.get("location", "")

        text = f"Calendar event: {title}"
        if description:
            text += f"\n{description}"
        if location:
            text += f"\nLocation: {location}"
        if attendees:
            text += f"\nAttendees: {', '.join(attendees)}"

        return self.store(
            text=text,
            id=f"cal_{event_data.get('id', '')}",
            source="calendar",
            source_type="calendar",
            contacts=attendees,
            metadata={
                "start_time": event_data.get("start_time", ""),
                "end_time": event_data.get("end_time", ""),
                "duration_minutes": event_data.get("duration_minutes", 0),
            },
        )


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _generate_id(text: str, source: str) -> str:
    """Generate a deterministic ID from text + source."""
    import hashlib
    content = f"{source}:{text[:200]}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _sanitize_fts_query(query: str) -> str:
    """Sanitize a query string for FTS5.

    FTS5 uses special syntax characters. We need to quote user input
    to avoid syntax errors.
    """
    # Remove FTS5 operator characters that could cause syntax errors
    # Keep alphanumeric, spaces, and basic punctuation
    cleaned = ""
    for c in query:
        if c.isalnum() or c in " .-_@":
            cleaned += c
        else:
            cleaned += " "

    # Split into words and join with OR for fuzzy matching
    words = [w.strip() for w in cleaned.split() if w.strip()]
    if not words:
        return ""

    # Use quoted terms for exact word matching
    quoted = [f'"{w}"' for w in words]
    return " OR ".join(quoted)


def _row_to_doc(row: sqlite3.Row) -> MemoryDocument:
    """Convert a sqlite3.Row to a MemoryDocument."""
    contacts = row["contacts"] if "contacts" in row.keys() else "[]"
    if isinstance(contacts, str):
        contacts = json.loads(contacts) if contacts else []

    metadata = row["metadata"] if "metadata" in row.keys() else "{}"
    if isinstance(metadata, str):
        metadata = json.loads(metadata) if metadata else {}

    # rank column exists in FTS5 join queries
    score = 0.0
    if "rank" in row.keys():
        # FTS5 rank is negative (lower = better). Convert to positive score.
        score = -float(row["rank"]) if row["rank"] else 0.0

    return MemoryDocument(
        id=row["id"],
        text=row["text"],
        source=row["source"],
        source_type=row["source_type"],
        timestamp=row["timestamp"],
        contacts=contacts,
        metadata=metadata,
        score=score,
    )
