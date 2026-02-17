"""
OmniBrain — Database Layer

SQLite database with all table schemas from the manifesto.
Handles initialization, migrations, and all CRUD operations.

Tables:
    events       — Core event stream (every collected event)
    contacts     — Contact knowledge base
    proposals    — Action proposals (OmniBrain proposes, user approves)
    observations — Behavioral observations (for pattern detection)
    preferences  — Learned user preferences
    briefings    — Briefing history
    agent_sessions — Omnigent session persistence

Uses FTS5 for full-text search across events.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator

from omnibrain.models import (
    ActionProposal,
    Briefing,
    ContactInfo,
    Observation,
    ProposalStatus,
)

logger = logging.getLogger("omnibrain.db")

# ═══════════════════════════════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════════════════════════════

SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Core event stream — every collected event goes here
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    metadata TEXT,
    processed BOOLEAN DEFAULT 0,
    priority INTEGER DEFAULT 0,
    UNIQUE(source, event_type, title, timestamp) ON CONFLICT REPLACE
);

-- Contacts knowledge base
CREATE TABLE IF NOT EXISTS contacts (
    email TEXT PRIMARY KEY,
    name TEXT,
    relationship TEXT DEFAULT 'unknown',
    organization TEXT,
    last_interaction TEXT,
    interaction_count INTEGER DEFAULT 0,
    avg_response_time_hours REAL DEFAULT 0.0,
    notes TEXT,
    metadata TEXT
);

-- Action proposals (OmniBrain proposes, user approves)
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    action_data TEXT,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 2,
    expires_at TEXT,
    result TEXT
);

-- Observations (for pattern detection)
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    pattern_type TEXT NOT NULL,
    description TEXT NOT NULL,
    frequency INTEGER DEFAULT 1,
    last_seen TEXT,
    confidence REAL DEFAULT 0.5,
    promoted_to_automation BOOLEAN DEFAULT 0
);

-- User preferences (learned)
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    learned_from TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Briefing history
CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    events_processed INTEGER DEFAULT 0,
    actions_proposed INTEGER DEFAULT 0,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(type, date) ON CONFLICT REPLACE
);

-- Omnigent session data (persists reasoning state)
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    task_type TEXT,
    state_json TEXT,
    profile_json TEXT,
    plan_json TEXT,
    graph_json TEXT,
    status TEXT DEFAULT 'active'
);

-- Installed Skills (Skill Protocol)
CREATE TABLE IF NOT EXISTS installed_skills (
    name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    description TEXT,
    author TEXT,
    category TEXT DEFAULT 'other',
    permissions TEXT,
    enabled BOOLEAN DEFAULT 1,
    installed_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    settings TEXT,
    data TEXT
);

-- Chat message history (persistent conversations)
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL DEFAULT 'default',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    metadata TEXT
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Full-text search on events
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    title,
    content,
    metadata,
    content='events',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, title, content, metadata)
    VALUES (new.id, new.title, new.content, new.metadata);
END;

CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, content, metadata)
    VALUES ('delete', old.id, old.title, old.content, old.metadata);
END;

CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, content, metadata)
    VALUES ('delete', old.id, old.title, old.content, old.metadata);
    INSERT INTO events_fts(rowid, title, content, metadata)
    VALUES (new.id, new.title, new.content, new.metadata);
END;

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_observations_type ON observations(pattern_type);
CREATE INDEX IF NOT EXISTS idx_briefings_date ON briefings(date);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON agent_sessions(status);
CREATE INDEX IF NOT EXISTS idx_skills_enabled ON installed_skills(enabled);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_timestamp ON chat_messages(timestamp);
"""


# ═══════════════════════════════════════════════════════════════════════════
# Database Manager
# ═══════════════════════════════════════════════════════════════════════════


class OmniBrainDB:
    """SQLite database manager for OmniBrain.

    Thread-safe via connection-per-call pattern.
    All writes go through context manager for automatic rollback on error.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.db_path = data_dir / "omnibrain.db"
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Create tables if they don't exist and run migrations."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            # Set schema version
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            # Migration: add UNIQUE constraint to events if missing
            self._migrate_events_unique(conn)
            # Migration: add snoozed_until column to proposals if missing
            self._migrate_proposals_snooze(conn)
            # Migration: add UNIQUE constraint + generated_at to briefings if missing
            self._migrate_briefings_unique(conn)
        logger.info(f"Database initialized at {self.db_path}")

    def _migrate_events_unique(self, conn: sqlite3.Connection) -> None:
        """Ensure events table has the UNIQUE constraint on (source, event_type, title, timestamp)."""
        # Check if the constraint already exists by inspecting the CREATE TABLE statement
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='events'"
        ).fetchone()
        if row and "UNIQUE" not in (row[0] or ""):
            logger.info("Migrating events table: adding UNIQUE constraint")
            # Deduplicate existing data first
            conn.execute(
                """DELETE FROM events WHERE rowid NOT IN (
                       SELECT MIN(rowid) FROM events
                       GROUP BY source, event_type, title, timestamp
                   )"""
            )
            # Rebuild table with constraint
            conn.execute("ALTER TABLE events RENAME TO events_old")
            conn.executescript("""
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT,
                    metadata TEXT,
                    processed BOOLEAN DEFAULT 0,
                    priority INTEGER DEFAULT 0,
                    UNIQUE(source, event_type, title, timestamp) ON CONFLICT REPLACE
                );
            """)
            conn.execute(
                """INSERT INTO events (id, timestamp, source, event_type, title,
                   content, metadata, processed, priority)
                   SELECT id, timestamp, source, event_type, title,
                   content, metadata, processed, priority FROM events_old"""
            )
            conn.execute("DROP TABLE events_old")
            # Rebuild FTS
            conn.execute("INSERT INTO events_fts(events_fts) VALUES('rebuild')")
            logger.info("Events table migration complete")

    def _migrate_proposals_snooze(self, conn: sqlite3.Connection) -> None:
        """Add snoozed_until column to proposals if missing."""
        cols = [r[1] for r in conn.execute("PRAGMA table_info(proposals)").fetchall()]
        if "snoozed_until" not in cols:
            conn.execute("ALTER TABLE proposals ADD COLUMN snoozed_until TEXT")
            logger.info("Added snoozed_until column to proposals")

    def _migrate_briefings_unique(self, conn: sqlite3.Connection) -> None:
        """Ensure briefings table has UNIQUE(type, date) and generated_at column."""
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='briefings'"
        ).fetchone()
        if row and "UNIQUE" not in (row[0] or ""):
            logger.info("Migrating briefings table: adding UNIQUE constraint + generated_at")
            conn.execute("ALTER TABLE briefings RENAME TO briefings_old")
            conn.executescript("""
                CREATE TABLE briefings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    events_processed INTEGER DEFAULT 0,
                    actions_proposed INTEGER DEFAULT 0,
                    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(type, date) ON CONFLICT REPLACE
                );
            """)
            conn.execute(
                """INSERT OR REPLACE INTO briefings (id, date, type, content,
                   events_processed, actions_proposed, generated_at)
                   SELECT id, date, type, content,
                   events_processed, actions_proposed, datetime('now')
                   FROM briefings_old"""
            )
            conn.execute("DROP TABLE briefings_old")
            logger.info("Briefings table migration complete")

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with WAL mode and foreign keys."""
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Events ──

    def insert_event(
        self,
        source: str,
        event_type: str,
        title: str,
        content: str = "",
        metadata: dict[str, Any] | None = None,
        priority: int = 0,
        timestamp: str | None = None,
    ) -> int:
        """Insert an event into the event stream. Returns the event ID."""
        with self._connect() as conn:
            if timestamp:
                cursor = conn.execute(
                    """INSERT INTO events (source, event_type, title, content, metadata, priority, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (source, event_type, title, content, json.dumps(metadata or {}), priority, timestamp),
                )
            else:
                cursor = conn.execute(
                    """INSERT INTO events (source, event_type, title, content, metadata, priority)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (source, event_type, title, content, json.dumps(metadata or {}), priority),
                )
            return cursor.lastrowid or 0

    def get_events(
        self,
        source: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        unprocessed_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Query events with optional filters."""
        query = "SELECT * FROM events WHERE 1=1"
        params: list[Any] = []

        if source:
            query += " AND source = ?"
            params.append(source)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if since:
            # Use replace to handle both 'T' and ' ' separators in stored timestamps
            ts = since.strftime("%Y-%m-%d %H:%M:%S")
            query += " AND replace(timestamp, 'T', ' ') >= ?"
            params.append(ts)
        if until:
            ts = until.strftime("%Y-%m-%d %H:%M:%S")
            query += " AND replace(timestamp, 'T', ' ') <= ?"
            params.append(ts)
        if unprocessed_only:
            query += " AND processed = 0"

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def mark_event_processed(self, event_id: int) -> None:
        """Mark an event as processed."""
        with self._connect() as conn:
            conn.execute("UPDATE events SET processed = 1 WHERE id = ?", (event_id,))

    def search_events(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text search across events."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT e.* FROM events e
                   JOIN events_fts f ON e.id = f.rowid
                   WHERE events_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    # ── Contacts ──

    def upsert_contact(self, contact: ContactInfo) -> None:
        """Insert or update a contact."""
        data = contact.to_dict()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO contacts (email, name, relationship, organization,
                   last_interaction, interaction_count, avg_response_time_hours, notes, metadata)
                   VALUES (:email, :name, :relationship, :organization,
                   :last_interaction, :interaction_count, :avg_response_time_hours, :notes, :metadata)
                   ON CONFLICT(email) DO UPDATE SET
                   name = COALESCE(NULLIF(excluded.name, ''), contacts.name),
                   relationship = CASE WHEN excluded.relationship != 'unknown'
                                       THEN excluded.relationship ELSE contacts.relationship END,
                   organization = COALESCE(NULLIF(excluded.organization, ''), contacts.organization),
                   last_interaction = COALESCE(excluded.last_interaction, contacts.last_interaction),
                   interaction_count = contacts.interaction_count + 1,
                   notes = COALESCE(NULLIF(excluded.notes, ''), contacts.notes),
                   metadata = excluded.metadata""",
                data,
            )

    def upsert_contact_by_name(
        self,
        name: str,
        relationship: str = "other",
        notes: str = "",
    ) -> None:
        """Upsert a contact by name (when email is unknown, e.g. from chat extraction).

        Uses a synthetic email placeholder so the contact can still be tracked.
        If a contact with the same name already exists, updates the record.
        """
        # Generate a stable placeholder email from the name
        slug = name.lower().replace(" ", ".").strip(".")
        placeholder_email = f"{slug}@contact.local"

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO contacts (email, name, relationship, notes, last_interaction, interaction_count)
                   VALUES (?, ?, ?, ?, datetime('now'), 1)
                   ON CONFLICT(email) DO UPDATE SET
                   name = COALESCE(NULLIF(excluded.name, ''), contacts.name),
                   relationship = CASE WHEN excluded.relationship != 'other'
                                       THEN excluded.relationship ELSE contacts.relationship END,
                   notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE contacts.notes END,
                   last_interaction = datetime('now'),
                   interaction_count = contacts.interaction_count + 1""",
                (placeholder_email, name, relationship, notes),
            )

    def get_contact(self, email: str) -> ContactInfo | None:
        """Get a contact by email."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM contacts WHERE email = ?", (email,)).fetchone()
            if row:
                return ContactInfo.from_dict(dict(row))
            return None

    def get_contacts(self, limit: int = 100) -> list[ContactInfo]:
        """Get all contacts ordered by interaction count."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts ORDER BY interaction_count DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [ContactInfo.from_dict(dict(row)) for row in rows]

    def get_vip_contacts(self) -> list[ContactInfo]:
        """Get VIP contacts (high interaction, fast response)."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM contacts
                   WHERE interaction_count >= 10 AND avg_response_time_hours < 4.0
                   ORDER BY interaction_count DESC""",
            ).fetchall()
            return [ContactInfo.from_dict(dict(row)) for row in rows]

    # ── Proposals ──

    def insert_proposal(
        self,
        type: str,
        title: str,
        description: str,
        action_data: dict[str, Any] | None = None,
        priority: int = 2,
        expires_at: datetime | None = None,
    ) -> int:
        """Create a new proposal. Returns the proposal ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO proposals (type, title, description, action_data, priority, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (type, title, description, json.dumps(action_data or {}), priority,
                 expires_at.isoformat() if expires_at else None),
            )
            return cursor.lastrowid or 0

    def get_pending_proposals(self) -> list[dict[str, Any]]:
        """Get all pending proposals."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM proposals
                   WHERE status = 'pending'
                   ORDER BY priority DESC, created_at ASC""",
            ).fetchall()
            return [dict(row) for row in rows]

    def update_proposal_status(self, proposal_id: int, status: str, result: str = "") -> bool:
        """Update a proposal's status. Returns True if found."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE proposals SET status = ?, result = ? WHERE id = ?",
                (status, result, proposal_id),
            )
            return cursor.rowcount > 0

    def expire_old_proposals(self) -> int:
        """Mark expired proposals. Returns count expired."""
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE proposals SET status = 'expired'
                   WHERE status = 'pending' AND expires_at IS NOT NULL
                   AND replace(expires_at, 'T', ' ') < datetime('now')""",
            )
            return cursor.rowcount

    # ── Observations ──

    def insert_observation(self, observation: Observation) -> int:
        """Record a behavioral observation."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO observations (pattern_type, description, frequency, last_seen, confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    observation.type,
                    observation.detail,
                    observation.frequency,
                    observation.timestamp.isoformat(),
                    observation.confidence,
                ),
            )
            return cursor.lastrowid or 0

    def get_observations(
        self,
        pattern_type: str | None = None,
        min_confidence: float = 0.0,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get observations with optional filters."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        query = "SELECT * FROM observations WHERE confidence >= ?"
        params: list[Any] = [min_confidence]

        if pattern_type:
            query += " AND pattern_type = ?"
            params.append(pattern_type)

        query += " AND timestamp >= ?"
        params.append(cutoff)
        query += " ORDER BY timestamp DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def promote_observation(self, observation_id: int) -> None:
        """Mark an observation as promoted to automation."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE observations SET promoted_to_automation = 1 WHERE id = ?",
                (observation_id,),
            )

    # ── Preferences ──

    def set_preference(self, key: str, value: Any, confidence: float = 0.5, learned_from: str = "") -> None:
        """Set or update a user preference."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO preferences (key, value, confidence, learned_from, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   confidence = excluded.confidence,
                   learned_from = excluded.learned_from,
                   updated_at = datetime('now')""",
                (key, json.dumps(value), confidence, learned_from),
            )

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
            if row:
                return json.loads(row["value"])
            return default

    def get_all_preferences(self) -> dict[str, Any]:
        """Get all preferences as a dict."""
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM preferences").fetchall()
            return {row["key"]: json.loads(row["value"]) for row in rows}

    # ── Briefings ──

    def insert_briefing(self, briefing: Briefing) -> int:
        """Store a generated briefing."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO briefings (date, type, content, events_processed, actions_proposed)
                   VALUES (?, ?, ?, ?, ?)""",
                (briefing.date, briefing.type, briefing.content,
                 briefing.events_processed, briefing.actions_proposed),
            )
            return cursor.lastrowid or 0

    def get_latest_briefing(self, briefing_type: str = "morning") -> dict[str, Any] | None:
        """Get the most recent briefing of a given type."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM briefings WHERE type = ?
                   ORDER BY date DESC LIMIT 1""",
                (briefing_type,),
            ).fetchone()
            return dict(row) if row else None

    # ── Agent Sessions ──

    def save_agent_session(
        self,
        session_id: str,
        task_type: str,
        state_json: str = "",
        profile_json: str = "",
        plan_json: str = "",
        graph_json: str = "",
    ) -> None:
        """Save or update an agent session."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_sessions (id, created_at, task_type, state_json,
                   profile_json, plan_json, graph_json, status)
                   VALUES (?, datetime('now'), ?, ?, ?, ?, ?, 'active')
                   ON CONFLICT(id) DO UPDATE SET
                   state_json = excluded.state_json,
                   profile_json = excluded.profile_json,
                   plan_json = excluded.plan_json,
                   graph_json = excluded.graph_json""",
                (session_id, task_type, state_json, profile_json, plan_json, graph_json),
            )

    def get_agent_session(self, session_id: str) -> dict[str, Any] | None:
        """Get an agent session by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    def close_agent_session(self, session_id: str) -> None:
        """Mark an agent session as completed."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE agent_sessions SET status = 'completed' WHERE id = ?",
                (session_id,),
            )

    # ── Installed Skills ──

    def install_skill(
        self,
        name: str,
        version: str,
        description: str = "",
        author: str = "",
        category: str = "other",
        permissions: list[str] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        """Record a Skill as installed."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO installed_skills
                   (name, version, description, author, category, permissions, settings)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                   version = excluded.version,
                   description = excluded.description,
                   permissions = excluded.permissions,
                   settings = excluded.settings,
                   updated_at = datetime('now')""",
                (name, version, description, author, category,
                 json.dumps(permissions or []), json.dumps(settings or {})),
            )

    def remove_skill(self, name: str) -> bool:
        """Remove an installed Skill.  Returns True if it existed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM installed_skills WHERE name = ?", (name,)
            )
            return cursor.rowcount > 0

    def get_installed_skills(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """List installed Skills."""
        query = "SELECT * FROM installed_skills"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query).fetchall()]

    def get_installed_skill(self, name: str) -> dict[str, Any] | None:
        """Get a single installed Skill by *name*."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM installed_skills WHERE name = ?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def set_skill_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a Skill.  Returns True if found."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE installed_skills SET enabled = ? WHERE name = ?",
                (1 if enabled else 0, name),
            )
            return cursor.rowcount > 0

    def set_skill_data(self, name: str, data: dict[str, Any]) -> None:
        """Store arbitrary Skill-level data."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE installed_skills SET data = ? WHERE name = ?",
                (json.dumps(data), name),
            )

    def get_skill_data(self, name: str) -> dict[str, Any]:
        """Retrieve Skill-level data."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM installed_skills WHERE name = ?", (name,)
            ).fetchone()
            if row and row["data"]:
                return json.loads(row["data"])
            return {}

    # ── Chat Messages ──

    def save_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Save a chat message. Returns the message ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO chat_messages (session_id, role, content, metadata)
                   VALUES (?, ?, ?, ?)""",
                (session_id, role, content, json.dumps(metadata or {})),
            )
            return cursor.lastrowid or 0

    def get_chat_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get chat messages for a session, ordered by timestamp."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM chat_messages
                   WHERE session_id = ?
                   ORDER BY timestamp ASC
                   LIMIT ?""",
                (session_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_chat_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent chat sessions with their last message."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT session_id,
                          COUNT(*) as message_count,
                          MIN(timestamp) as started_at,
                          MAX(timestamp) as last_message_at
                   FROM chat_messages
                   GROUP BY session_id
                   ORDER BY last_message_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_chat_session(self, session_id: str) -> int:
        """Delete all messages in a chat session. Returns count deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )
            return cursor.rowcount

    # ── Stats ──

    def get_stats(self) -> dict[str, int]:
        """Get overall database statistics."""
        stats = {}
        with self._connect() as conn:
            stats["events"] = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            stats["contacts"] = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
            stats["proposals_pending"] = conn.execute(
                "SELECT COUNT(*) FROM proposals WHERE status = 'pending'"
            ).fetchone()[0]
            stats["proposals_total"] = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
            stats["observations"] = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            stats["briefings"] = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]
            stats["active_sessions"] = conn.execute(
                "SELECT COUNT(*) FROM agent_sessions WHERE status = 'active'"
            ).fetchone()[0]
            stats["installed_skills"] = conn.execute(
                "SELECT COUNT(*) FROM installed_skills"
            ).fetchone()[0]
            stats["chat_messages"] = conn.execute(
                "SELECT COUNT(*) FROM chat_messages"
            ).fetchone()[0]
            stats["chat_sessions"] = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM chat_messages"
            ).fetchone()[0]
        return stats

    # ── Maintenance ──

    def prune_old_data(self, event_days: int = 365, proposal_days: int = 90, session_days: int = 30) -> dict[str, int]:
        """Prune old data according to retention policy. Returns counts deleted."""
        deleted = {}
        event_cutoff = (datetime.now() - timedelta(days=event_days)).isoformat()
        proposal_cutoff = (datetime.now() - timedelta(days=proposal_days)).isoformat()
        session_cutoff = (datetime.now() - timedelta(days=session_days)).isoformat()

        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE timestamp < ?",
                (event_cutoff,),
            )
            deleted["events"] = cursor.rowcount

            cursor = conn.execute(
                """DELETE FROM proposals WHERE status IN ('executed', 'rejected', 'expired')
                    AND created_at < ?""",
                (proposal_cutoff,),
            )
            deleted["proposals"] = cursor.rowcount

            cursor = conn.execute(
                """DELETE FROM agent_sessions WHERE status = 'completed'
                    AND created_at < ?""",
                (session_cutoff,),
            )
            deleted["sessions"] = cursor.rowcount

        if any(deleted.values()):
            logger.info(f"Pruned old data: {deleted}")
        return deleted

    def vacuum(self) -> None:
        """Compact the database file."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("VACUUM")
        conn.close()

    def export_all(self, output_dir: Path) -> None:
        """Export all data as JSON files (GDPR compliance)."""
        output_dir.mkdir(parents=True, exist_ok=True)
        tables = ["events", "contacts", "proposals", "observations", "preferences", "briefings", "installed_skills"]
        with self._connect() as conn:
            for table in tables:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                data = [dict(row) for row in rows]
                with open(output_dir / f"{table}.json", "w") as f:
                    json.dump(data, f, indent=2, default=str)
        logger.info(f"Exported all data to {output_dir}")

    def wipe_all(self) -> None:
        """Delete ALL data. GDPR right to delete."""
        with self._connect() as conn:
            for table in ["events", "contacts", "proposals", "observations",
                          "preferences", "briefings", "agent_sessions",
                          "installed_skills", "chat_messages"]:
                conn.execute(f"DELETE FROM {table}")
        self.vacuum()
        logger.warning("All data wiped.")
