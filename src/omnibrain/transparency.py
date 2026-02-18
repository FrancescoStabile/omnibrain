"""
OmniBrain — Transparency Log

Full audit trail of every LLM call OmniBrain makes. The manifesto
guarantees: "A local log of all outgoing prompts is maintained."

Architecture:
    - Each LLM invocation is logged to ``llm_calls`` table in SQLite
    - The ``TransparencyLogger`` wraps ``LLMRouter.stream()`` as a decorator
    - API routes expose paginated call history + aggregated stats
    - Frontend shows a "Transparency" page with table + cost charts

This module is the trust backbone. Every token that leaves the user's
machine is accounted for here.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("omnibrain.transparency")


# ═══════════════════════════════════════════════════════════════════════════
# Schema — extends the main DB
# ═══════════════════════════════════════════════════════════════════════════

TRANSPARENCY_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    provider TEXT NOT NULL,
    model TEXT,
    prompt_preview TEXT,
    prompt_hash TEXT,
    prompt_size_bytes INTEGER DEFAULT 0,
    response_size_bytes INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_estimate REAL DEFAULT 0.0,
    source TEXT DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT 1,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_timestamp ON llm_calls(timestamp);
CREATE INDEX IF NOT EXISTS idx_llm_calls_provider ON llm_calls(provider);
CREATE INDEX IF NOT EXISTS idx_llm_calls_source ON llm_calls(source);
"""


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class LLMCallRecord:
    """A single logged LLM invocation."""

    id: int = 0
    timestamp: str = ""
    provider: str = ""
    model: str = ""
    prompt_preview: str = ""
    prompt_hash: str = ""
    prompt_size_bytes: int = 0
    response_size_bytes: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_estimate: float = 0.0
    source: str = ""
    duration_ms: int = 0
    success: bool = True
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "prompt_preview": self.prompt_preview,
            "prompt_hash": self.prompt_hash,
            "system_prompt_hash": self.prompt_hash,
            "prompt_size_bytes": self.prompt_size_bytes,
            "response_size_bytes": self.response_size_bytes,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost_estimate": self.cost_estimate,
            "cost_usd": self.cost_estimate,
            "source": self.source,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "had_error": not self.success,
            "had_tools": False,
            "error_message": self.error_message,
        }


@dataclass
class TransparencyStats:
    """Aggregated transparency statistics."""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    calls_by_provider: dict[str, int] = field(default_factory=dict)
    cost_by_provider: dict[str, float] = field(default_factory=dict)
    calls_by_source: dict[str, int] = field(default_factory=dict)
    avg_duration_ms: float = 0.0
    calls_today: int = 0
    cost_today: float = 0.0
    cost_this_month: float = 0.0
    bytes_sent_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        # Merge provider calls + costs into a single nested dict (matches frontend schema)
        by_provider: dict[str, dict[str, Any]] = {}
        for provider, calls in self.calls_by_provider.items():
            by_provider[provider] = {
                "calls": calls,
                "cost": round(self.cost_by_provider.get(provider, 0.0), 6),
            }

        # Merge source calls into a nested dict (frontend expects by_source.calls)
        by_source: dict[str, dict[str, Any]] = {
            source: {"calls": calls, "cost": 0.0}
            for source, calls in self.calls_by_source.items()
        }

        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            # Legacy key kept for backward compat
            "total_cost": round(self.total_cost, 6),
            "by_provider": by_provider,
            "by_source": by_source,
            # Legacy keys kept for backward compat
            "calls_by_provider": self.calls_by_provider,
            "cost_by_provider": {k: round(v, 6) for k, v in self.cost_by_provider.items()},
            "calls_by_source": self.calls_by_source,
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "calls_today": self.calls_today,
            "cost_today": round(self.cost_today, 6),
            "cost_this_month": round(self.cost_this_month, 6),
            "bytes_sent_total": self.bytes_sent_total,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Transparency Logger
# ═══════════════════════════════════════════════════════════════════════════


class TransparencyLogger:
    """Logs every LLM call to SQLite for full auditability.

    Designed to wrap LLMRouter.stream() with zero overhead on the
    streaming path — the write happens after the stream completes.

    Usage::

        tlog = TransparencyLogger(data_dir)
        # Easy: log manually
        tlog.log_call(provider="deepseek", model="deepseek-chat", ...)
        # Or: wrap a router stream
        async for chunk in tlog.wrap_stream(router.stream(...), source="chat"):
            ...
    """

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "omnibrain.db"
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create transparency tables if they don't exist."""
        try:
            with self._connect() as conn:
                conn.executescript(TRANSPARENCY_SCHEMA)
        except Exception as e:
            logger.error(f"Failed to create transparency schema: {e}")

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────
    # Core logging
    # ──────────────────────────────────────────────────────────

    def log_call(
        self,
        *,
        provider: str,
        model: str = "",
        prompt_text: str = "",
        response_text: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        cost_estimate: float = 0.0,
        source: str = "",
        duration_ms: int = 0,
        success: bool = True,
        error_message: str = "",
    ) -> int:
        """Log a single LLM call. Returns the row ID."""
        prompt_preview = prompt_text[:500] if prompt_text else ""
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest() if prompt_text else ""
        prompt_size = len(prompt_text.encode()) if prompt_text else 0
        response_size = len(response_text.encode()) if response_text else 0

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """INSERT INTO llm_calls
                       (provider, model, prompt_preview, prompt_hash,
                        prompt_size_bytes, response_size_bytes,
                        input_tokens, output_tokens,
                        cache_read_tokens, cache_creation_tokens,
                        cost_estimate, source, duration_ms, success, error_message)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        provider, model, prompt_preview, prompt_hash,
                        prompt_size, response_size,
                        input_tokens, output_tokens,
                        cache_read_tokens, cache_creation_tokens,
                        cost_estimate, source, duration_ms, success, error_message,
                    ),
                )
                return cursor.lastrowid or 0
        except Exception as e:
            logger.error(f"Failed to log LLM call: {e}")
            return 0

    async def wrap_stream(
        self,
        stream: AsyncGenerator,
        *,
        source: str = "",
        provider: str = "",
        prompt_text: str = "",
    ) -> AsyncGenerator:
        """Wrap an LLMRouter stream, accumulate metadata, log on completion.

        This is a transparent passthrough — the caller gets identical
        StreamChunk objects. The log write happens after the stream ends.
        """
        from omnigent.cost_tracker import PRICING

        start_time = time.monotonic()
        response_parts: list[str] = []
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_creation = 0
        model = ""
        success = True
        error_msg = ""

        try:
            async for chunk in stream:
                # Accumulate metadata from chunks
                if chunk.content:
                    response_parts.append(chunk.content)
                if chunk.model:
                    model = chunk.model
                if chunk.input_tokens:
                    total_input += chunk.input_tokens
                if chunk.output_tokens:
                    total_output += chunk.output_tokens
                if chunk.cache_read_tokens:
                    total_cache_read += chunk.cache_read_tokens
                if chunk.cache_creation_tokens:
                    total_cache_creation += chunk.cache_creation_tokens
                yield chunk
        except Exception as e:
            success = False
            error_msg = str(e)[:500]
            raise
        finally:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            response_text = "".join(response_parts)

            # Compute cost from pricing table
            cost = 0.0
            provider_key = provider.lower()
            if provider_key in PRICING:
                pricing = PRICING[provider_key]
                cost = (
                    (total_input / 1_000_000) * pricing.input_per_million
                    + (total_output / 1_000_000) * pricing.output_per_million
                    + (total_cache_read / 1_000_000) * pricing.cache_read_per_million
                    + (total_cache_creation / 1_000_000) * pricing.cache_creation_per_million
                )

            self.log_call(
                provider=provider or "unknown",
                model=model,
                prompt_text=prompt_text,
                response_text=response_text,
                input_tokens=total_input,
                output_tokens=total_output,
                cache_read_tokens=total_cache_read,
                cache_creation_tokens=total_cache_creation,
                cost_estimate=cost,
                source=source,
                duration_ms=duration_ms,
                success=success,
                error_message=error_msg,
            )

    def log_from_hook(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_creation_tokens: int,
        source: str,
    ) -> None:
        """Convenience callback for LLMRouter.set_stream_hook().

        Called automatically after every stream completes when the hook is
        registered on the router. Computes cost from the PRICING table and
        persists a log record. Sync-safe (no async needed).
        """
        from omnigent.cost_tracker import PRICING

        cost = 0.0
        provider_key = provider.lower()
        if provider_key in PRICING:
            p = PRICING[provider_key]
            cost = (
                (input_tokens / 1_000_000) * p.input_per_million
                + (output_tokens / 1_000_000) * p.output_per_million
                + (cache_read_tokens / 1_000_000) * p.cache_read_per_million
                + (cache_creation_tokens / 1_000_000) * p.cache_creation_per_million
            )

        self.log_call(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cost_estimate=cost,
            source=source or "unknown",
        )

    # ──────────────────────────────────────────────────────────
    # Queries
    # ──────────────────────────────────────────────────────────

    def get_calls(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        provider: str = "",
        source: str = "",
        since: str = "",
        until: str = "",
    ) -> list[LLMCallRecord]:
        """Get paginated LLM call history with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until:
            conditions.append("timestamp <= ?")
            params.append(until)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"SELECT * FROM llm_calls {where} ORDER BY id DESC LIMIT ? OFFSET ?",  # noqa: S608
                    (*params, limit, offset),
                ).fetchall()
                return [
                    LLMCallRecord(
                        id=r["id"],
                        timestamp=r["timestamp"],
                        provider=r["provider"],
                        model=r["model"] or "",
                        prompt_preview=r["prompt_preview"] or "",
                        prompt_hash=r["prompt_hash"] or "",
                        prompt_size_bytes=r["prompt_size_bytes"] or 0,
                        response_size_bytes=r["response_size_bytes"] or 0,
                        input_tokens=r["input_tokens"] or 0,
                        output_tokens=r["output_tokens"] or 0,
                        cache_read_tokens=r["cache_read_tokens"] or 0,
                        cache_creation_tokens=r["cache_creation_tokens"] or 0,
                        cost_estimate=r["cost_estimate"] or 0.0,
                        source=r["source"] or "",
                        duration_ms=r["duration_ms"] or 0,
                        success=bool(r["success"]),
                        error_message=r["error_message"] or "",
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Failed to query LLM calls: {e}")
            return []

    def get_stats(self, days: int = 0) -> TransparencyStats:
        """Get aggregated transparency statistics.

        Args:
            days: If > 0, only include calls from the last N days.
                  If 0, include all calls.
        """
        stats = TransparencyStats()
        time_filter = ""
        params: list[Any] = []

        if days > 0:
            since = (datetime.now() - timedelta(days=days)).isoformat()
            time_filter = "WHERE timestamp >= ?"
            params = [since]

        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row

                # Overall totals
                row = conn.execute(
                    f"""SELECT
                        COUNT(*) as total,
                        COALESCE(SUM(input_tokens), 0) as total_in,
                        COALESCE(SUM(output_tokens), 0) as total_out,
                        COALESCE(SUM(cost_estimate), 0) as total_cost,
                        COALESCE(AVG(duration_ms), 0) as avg_ms,
                        COALESCE(SUM(prompt_size_bytes), 0) as bytes_sent
                    FROM llm_calls {time_filter}""",
                    params,
                ).fetchone()
                if row:
                    stats.total_calls = row["total"]
                    stats.total_input_tokens = row["total_in"]
                    stats.total_output_tokens = row["total_out"]
                    stats.total_cost = row["total_cost"]
                    stats.avg_duration_ms = row["avg_ms"]
                    stats.bytes_sent_total = row["bytes_sent"]

                # By provider
                for r in conn.execute(
                    f"""SELECT provider, COUNT(*) as cnt, COALESCE(SUM(cost_estimate), 0) as cost
                        FROM llm_calls {time_filter}
                        GROUP BY provider""",
                    params,
                ).fetchall():
                    stats.calls_by_provider[r["provider"]] = r["cnt"]
                    stats.cost_by_provider[r["provider"]] = r["cost"]

                # By source
                for r in conn.execute(
                    f"""SELECT source, COUNT(*) as cnt
                        FROM llm_calls {time_filter}
                        GROUP BY source""",
                    params,
                ).fetchall():
                    stats.calls_by_source[r["source"] or "unknown"] = r["cnt"]

                # Today
                today = datetime.now().strftime("%Y-%m-%d")
                today_row = conn.execute(
                    """SELECT COUNT(*) as cnt, COALESCE(SUM(cost_estimate), 0) as cost
                       FROM llm_calls WHERE timestamp >= ?""",
                    (today,),
                ).fetchone()
                if today_row:
                    stats.calls_today = today_row["cnt"]
                    stats.cost_today = today_row["cost"]

                # This month
                month_start = datetime.now().strftime("%Y-%m-01")
                month_row = conn.execute(
                    """SELECT COALESCE(SUM(cost_estimate), 0) as cost
                       FROM llm_calls WHERE timestamp >= ?""",
                    (month_start,),
                ).fetchone()
                if month_row:
                    stats.cost_this_month = month_row["cost"]

        except Exception as e:
            logger.error(f"Failed to compute transparency stats: {e}")

        return stats

    def get_daily_costs(self, days: int = 30) -> list[dict[str, Any]]:
        """Get daily cost breakdown for charting."""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT DATE(timestamp) as day,
                              provider,
                              COUNT(*) as calls,
                              COALESCE(SUM(cost_estimate), 0) as cost,
                              COALESCE(SUM(input_tokens), 0) as input_tokens,
                              COALESCE(SUM(output_tokens), 0) as output_tokens
                       FROM llm_calls
                       WHERE timestamp >= ?
                       GROUP BY day, provider
                       ORDER BY day""",
                    (since,),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to get daily costs: {e}")
            return []

    def prune(self, days: int = 90) -> int:
        """Remove log entries older than N days. Returns count deleted."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM llm_calls WHERE timestamp < ?",
                    (cutoff,),
                )
                deleted = cursor.rowcount
                if deleted:
                    logger.info(f"Transparency log: pruned {deleted} entries older than {days} days")
                return deleted
        except Exception as e:
            logger.error(f"Failed to prune transparency log: {e}")
            return 0
