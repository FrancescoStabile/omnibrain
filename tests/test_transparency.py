"""
Tests for Transparency Logger — LLM call logging, querying, stats, and pruning.

Groups:
    LogCall     — log_call() writes correct data
    GetCalls    — pagination, provider/source/date filters
    GetStats    — aggregated stats correctness
    DailyCosts  — daily breakdown for charting
    Prune       — old record removal
    WrapStream  — stream wrapper passthrough + logging
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnibrain.transparency import TransparencyLogger, TransparencyStats, LLMCallRecord


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_logger(tmp_path):
    """Create a TransparencyLogger backed by a temp SQLite DB."""
    return TransparencyLogger(tmp_path)


def _insert_call(logger: TransparencyLogger, **kwargs) -> int:
    """Helper to insert a call with sensible defaults."""
    defaults = {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "prompt_text": "hello world",
        "response_text": "hi there",
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_estimate": 0.001,
        "source": "chat",
        "duration_ms": 200,
        "success": True,
    }
    defaults.update(kwargs)
    return logger.log_call(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# LogCall
# ═══════════════════════════════════════════════════════════════════════════


class TestLogCall:
    def test_returns_row_id(self, tmp_logger):
        row_id = _insert_call(tmp_logger)
        assert row_id > 0

    def test_increments_row_id(self, tmp_logger):
        id1 = _insert_call(tmp_logger)
        id2 = _insert_call(tmp_logger)
        assert id2 > id1

    def test_prompt_preview_truncated_at_500(self, tmp_logger):
        long_prompt = "x" * 1000
        _insert_call(tmp_logger, prompt_text=long_prompt)
        calls = tmp_logger.get_calls()
        assert len(calls[0].prompt_preview) == 500

    def test_prompt_hash_computed(self, tmp_logger):
        _insert_call(tmp_logger, prompt_text="test prompt")
        call = tmp_logger.get_calls()[0]
        assert len(call.prompt_hash) == 64  # SHA-256 hex

    def test_empty_prompt_handled(self, tmp_logger):
        row_id = _insert_call(tmp_logger, prompt_text="")
        assert row_id > 0
        call = tmp_logger.get_calls()[0]
        assert call.prompt_hash == ""

    def test_failed_call_logged(self, tmp_logger):
        row_id = logger_insert = tmp_logger.log_call(
            provider="openai",
            model="gpt-4o",
            success=False,
            error_message="Rate limited",
        )
        assert row_id > 0
        call = tmp_logger.get_calls()[0]
        assert call.success is False
        assert "Rate limited" in call.error_message

    def test_prompt_size_bytes_stored(self, tmp_logger):
        prompt = "hello" * 10  # 50 bytes
        _insert_call(tmp_logger, prompt_text=prompt)
        call = tmp_logger.get_calls()[0]
        assert call.prompt_size_bytes == len(prompt.encode())

    def test_multiple_providers(self, tmp_logger):
        _insert_call(tmp_logger, provider="deepseek")
        _insert_call(tmp_logger, provider="claude")
        _insert_call(tmp_logger, provider="openai")
        calls = tmp_logger.get_calls()
        providers = {c.provider for c in calls}
        assert providers == {"deepseek", "claude", "openai"}


# ═══════════════════════════════════════════════════════════════════════════
# GetCalls — Filtering
# ═══════════════════════════════════════════════════════════════════════════


class TestGetCalls:
    def test_empty_db_returns_empty(self, tmp_logger):
        assert tmp_logger.get_calls() == []

    def test_limit(self, tmp_logger):
        for _ in range(10):
            _insert_call(tmp_logger)
        calls = tmp_logger.get_calls(limit=3)
        assert len(calls) == 3

    def test_offset(self, tmp_logger):
        for i in range(5):
            _insert_call(tmp_logger, source=f"s{i}")
        all_calls = tmp_logger.get_calls(limit=100)
        paged = tmp_logger.get_calls(limit=2, offset=2)
        assert paged == all_calls[2:4]

    def test_filter_by_provider(self, tmp_logger):
        _insert_call(tmp_logger, provider="deepseek")
        _insert_call(tmp_logger, provider="claude")
        result = tmp_logger.get_calls(provider="claude")
        assert len(result) == 1
        assert result[0].provider == "claude"

    def test_filter_by_source(self, tmp_logger):
        _insert_call(tmp_logger, source="briefing")
        _insert_call(tmp_logger, source="chat")
        result = tmp_logger.get_calls(source="briefing")
        assert len(result) == 1
        assert result[0].source == "briefing"

    def test_filter_by_since(self, tmp_logger):
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        _insert_call(tmp_logger)  # now
        result = tmp_logger.get_calls(since=future)
        assert result == []

    def test_filter_by_until(self, tmp_logger):
        # SQLite stores timestamps as 'YYYY-MM-DD HH:MM:SS' (space separator).
        # We filter until yesterday — the record inserted now should NOT appear.
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_call(tmp_logger)  # inserted now
        result = tmp_logger.get_calls(until=yesterday)
        assert result == []

    def test_combined_provider_and_source_filter(self, tmp_logger):
        _insert_call(tmp_logger, provider="deepseek", source="chat")
        _insert_call(tmp_logger, provider="deepseek", source="briefing")
        _insert_call(tmp_logger, provider="claude", source="chat")
        result = tmp_logger.get_calls(provider="deepseek", source="chat")
        assert len(result) == 1

    def test_returns_in_descending_id_order(self, tmp_logger):
        ids = [_insert_call(tmp_logger) for _ in range(5)]
        calls = tmp_logger.get_calls()
        returned_ids = [c.id for c in calls]
        assert returned_ids == sorted(ids, reverse=True)

    def test_record_fields_populated(self, tmp_logger):
        _insert_call(
            tmp_logger,
            provider="deepseek",
            model="deepseek-chat",
            input_tokens=100,
            output_tokens=50,
            cost_estimate=0.005,
            source="chat",
            duration_ms=350,
        )
        call = tmp_logger.get_calls()[0]
        assert call.provider == "deepseek"
        assert call.model == "deepseek-chat"
        assert call.input_tokens == 100
        assert call.output_tokens == 50
        assert abs(call.cost_estimate - 0.005) < 1e-9
        assert call.source == "chat"
        assert call.duration_ms == 350


# ═══════════════════════════════════════════════════════════════════════════
# GetStats
# ═══════════════════════════════════════════════════════════════════════════


class TestGetStats:
    def test_empty_db_returns_zero_stats(self, tmp_logger):
        stats = tmp_logger.get_stats()
        assert stats.total_calls == 0
        assert stats.total_cost == 0.0
        assert stats.calls_by_provider == {}

    def test_total_calls(self, tmp_logger):
        for _ in range(7):
            _insert_call(tmp_logger)
        assert tmp_logger.get_stats().total_calls == 7

    def test_total_tokens(self, tmp_logger):
        _insert_call(tmp_logger, input_tokens=100, output_tokens=50)
        _insert_call(tmp_logger, input_tokens=200, output_tokens=100)
        stats = tmp_logger.get_stats()
        assert stats.total_input_tokens == 300
        assert stats.total_output_tokens == 150

    def test_total_cost(self, tmp_logger):
        _insert_call(tmp_logger, cost_estimate=0.01)
        _insert_call(tmp_logger, cost_estimate=0.02)
        stats = tmp_logger.get_stats()
        assert abs(stats.total_cost - 0.03) < 1e-9

    def test_calls_by_provider(self, tmp_logger):
        _insert_call(tmp_logger, provider="deepseek")
        _insert_call(tmp_logger, provider="deepseek")
        _insert_call(tmp_logger, provider="claude")
        stats = tmp_logger.get_stats()
        assert stats.calls_by_provider["deepseek"] == 2
        assert stats.calls_by_provider["claude"] == 1

    def test_calls_by_source(self, tmp_logger):
        _insert_call(tmp_logger, source="chat")
        _insert_call(tmp_logger, source="briefing")
        _insert_call(tmp_logger, source="chat")
        stats = tmp_logger.get_stats()
        assert stats.calls_by_source["chat"] == 2
        assert stats.calls_by_source["briefing"] == 1

    def test_calls_today(self, tmp_logger):
        _insert_call(tmp_logger)  # inserted now → counts as today
        stats = tmp_logger.get_stats()
        assert stats.calls_today >= 1

    def test_stats_with_day_filter(self, tmp_logger):
        _insert_call(tmp_logger)
        stats = tmp_logger.get_stats(days=30)
        assert stats.total_calls >= 1

    def test_stats_to_dict(self, tmp_logger):
        _insert_call(tmp_logger, cost_estimate=0.0035)
        d = tmp_logger.get_stats().to_dict()
        assert "total_calls" in d
        assert "total_cost" in d
        assert "calls_by_provider" in d
        assert isinstance(d["total_cost"], float)


# ═══════════════════════════════════════════════════════════════════════════
# DailyCosts
# ═══════════════════════════════════════════════════════════════════════════


class TestDailyCosts:
    def test_empty_db_returns_empty(self, tmp_logger):
        assert tmp_logger.get_daily_costs() == []

    def test_today_entry_present(self, tmp_logger):
        _insert_call(tmp_logger, provider="deepseek", cost_estimate=0.01)
        daily = tmp_logger.get_daily_costs(days=7)
        assert len(daily) >= 1
        today = datetime.now().strftime("%Y-%m-%d")
        days_found = [d["day"] for d in daily]
        assert today in days_found

    def test_multiple_providers_per_day(self, tmp_logger):
        _insert_call(tmp_logger, provider="deepseek", cost_estimate=0.01)
        _insert_call(tmp_logger, provider="claude", cost_estimate=0.02)
        daily = tmp_logger.get_daily_costs(days=7)
        providers = {d["provider"] for d in daily}
        assert "deepseek" in providers
        assert "claude" in providers

    def test_cost_aggregated_per_day_provider(self, tmp_logger):
        _insert_call(tmp_logger, provider="deepseek", cost_estimate=0.01)
        _insert_call(tmp_logger, provider="deepseek", cost_estimate=0.02)
        daily = tmp_logger.get_daily_costs(days=7)
        today = datetime.now().strftime("%Y-%m-%d")
        ds_entry = next(
            (d for d in daily if d["provider"] == "deepseek" and d["day"] == today),
            None,
        )
        assert ds_entry is not None
        assert abs(ds_entry["cost"] - 0.03) < 1e-9


# ═══════════════════════════════════════════════════════════════════════════
# Prune
# ═══════════════════════════════════════════════════════════════════════════


class TestPrune:
    def test_prune_returns_zero_when_nothing_old(self, tmp_logger):
        _insert_call(tmp_logger)  # recent
        deleted = tmp_logger.prune(days=90)
        assert deleted == 0

    def test_prune_removes_old_records(self, tmp_logger, tmp_path):
        """Manually insert a row with old timestamp."""
        db_path = tmp_path / "omnibrain.db"
        # Use logger's own DB
        old_ts = (datetime.now() - timedelta(days=100)).isoformat()
        with sqlite3.connect(str(tmp_logger._db_path)) as conn:
            conn.execute(
                "INSERT INTO llm_calls (provider, timestamp) VALUES (?, ?)",
                ("old-provider", old_ts),
            )
        # Also insert a recent one
        _insert_call(tmp_logger)
        deleted = tmp_logger.prune(days=90)
        assert deleted == 1
        remaining = tmp_logger.get_calls()
        assert all(r.provider != "old-provider" for r in remaining)

    def test_prune_empty_db(self, tmp_logger):
        assert tmp_logger.prune(days=30) == 0


# ═══════════════════════════════════════════════════════════════════════════
# LLMCallRecord
# ═══════════════════════════════════════════════════════════════════════════


class TestLLMCallRecord:
    def test_to_dict(self):
        record = LLMCallRecord(
            id=1,
            provider="deepseek",
            model="deepseek-chat",
            input_tokens=100,
            output_tokens=50,
            cost_estimate=0.0015,
            success=True,
        )
        d = record.to_dict()
        assert d["provider"] == "deepseek"
        assert d["input_tokens"] == 100
        assert d["success"] is True

    def test_default_values(self):
        r = LLMCallRecord()
        assert r.id == 0
        assert r.success is True
        assert r.cost_estimate == 0.0
        assert r.provider == ""


# ═══════════════════════════════════════════════════════════════════════════
# WrapStream
# ═══════════════════════════════════════════════════════════════════════════


class TestWrapStream:
    @pytest.mark.asyncio
    async def test_passthrough_yields_all_chunks(self, tmp_logger):
        """wrap_stream must yield every chunk unmodified."""
        from dataclasses import dataclass

        @dataclass
        class FakeChunk:
            content: str = ""
            model: str = "deepseek-chat"
            input_tokens: int = 0
            output_tokens: int = 0
            cache_read_tokens: int = 0
            cache_creation_tokens: int = 0

        async def fake_stream():
            yield FakeChunk(content="hello", input_tokens=5)
            yield FakeChunk(content=" world", output_tokens=3)

        received = []
        async for chunk in tmp_logger.wrap_stream(
            fake_stream(),
            source="test",
            provider="deepseek",
            prompt_text="test prompt",
        ):
            received.append(chunk.content)

        assert received == ["hello", " world"]

    @pytest.mark.asyncio
    async def test_wrap_stream_logs_after_completion(self, tmp_logger):
        """wrap_stream must write to the DB after the stream ends."""
        from dataclasses import dataclass

        @dataclass
        class FakeChunk:
            content: str = ""
            model: str = "deepseek-chat"
            input_tokens: int = 10
            output_tokens: int = 5
            cache_read_tokens: int = 0
            cache_creation_tokens: int = 0

        async def fake_stream():
            yield FakeChunk(content="hi", input_tokens=10, output_tokens=5)

        assert tmp_logger.get_calls() == []

        async for _ in tmp_logger.wrap_stream(
            fake_stream(),
            source="chat",
            provider="deepseek",
        ):
            pass

        calls = tmp_logger.get_calls()
        assert len(calls) == 1
        assert calls[0].source == "chat"
        assert calls[0].input_tokens == 10
        assert calls[0].output_tokens == 5

    @pytest.mark.asyncio
    async def test_wrap_stream_logs_failure_on_exception(self, tmp_logger):
        """wrap_stream must log success=False if the stream raises."""
        from dataclasses import dataclass

        @dataclass
        class FakeChunk:
            content: str = ""
            model: str = ""
            input_tokens: int = 0
            output_tokens: int = 0
            cache_read_tokens: int = 0
            cache_creation_tokens: int = 0

        async def failing_stream():
            yield FakeChunk(content="start")
            raise RuntimeError("connection reset")

        with pytest.raises(RuntimeError):
            async for _ in tmp_logger.wrap_stream(
                failing_stream(),
                source="chat",
                provider="deepseek",
            ):
                pass

        calls = tmp_logger.get_calls()
        assert len(calls) == 1
        assert calls[0].success is False
        assert "connection reset" in calls[0].error_message
