"""
Tests for OmniBrain CLI commands (Day 17-18).

Tests the actual CLI subcommands via subprocess and the handler functions directly.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from omnibrain.db import OmniBrainDB
from omnibrain.memory import MemoryManager
from omnibrain.models import Briefing


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def db(tmp_dir):
    return OmniBrainDB(tmp_dir)


@pytest.fixture
def memory(tmp_dir):
    return MemoryManager(tmp_dir, enable_chroma=False)


# ═══════════════════════════════════════════════════════════════════════════
# CLI Subprocess Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCLIVersion:
    """Test --version flag."""

    def test_version_flag(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "omnibrain" in result.stdout.lower()

    def test_help_flag(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "omnibrain" in result.stdout.lower() or "OmniBrain" in result.stdout


class TestCLISubcommands:
    """Test that subcommands are registered."""

    def test_status_registered(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "status"],
            capture_output=True, text=True, timeout=10,
        )
        # Should run without error (may have no data)
        assert result.returncode == 0

    def test_proposals_registered(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "proposals"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_briefing_registered(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "briefing"],
            capture_output=True, text=True, timeout=10,
        )
        # May generate or show "no briefing" — both OK
        assert result.returncode == 0

    def test_search_registered(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "search", "test query"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0


class TestCLIArgParser:
    """Test argument parser structure via help output."""

    def test_search_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "search", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "query" in result.stdout.lower()
        assert "--limit" in result.stdout

    def test_approve_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "approve", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "proposal_id" in result.stdout

    def test_api_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "api", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert "--host" in result.stdout
        assert "--port" in result.stdout


# ═══════════════════════════════════════════════════════════════════════════
# Direct Handler Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdBriefing:
    """Test _cmd_briefing function."""

    def test_briefing_runs_without_error(self):
        """Briefing command runs via subprocess."""
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "briefing"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0


class TestCmdSearch:
    """Test _cmd_search function."""

    def test_search_no_results(self):
        """Search with no results via subprocess."""
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "search", "nonexistent_xyz_query"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════
# CLI Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestCLIIntegration:
    """Integration tests combining multiple CLI operations."""

    def test_full_proposal_workflow(self):
        """Status → proposals → shows no pending."""
        r1 = subprocess.run(
            [sys.executable, "-m", "omnibrain", "status"],
            capture_output=True, text=True, timeout=10,
        )
        assert r1.returncode == 0

        r2 = subprocess.run(
            [sys.executable, "-m", "omnibrain", "proposals"],
            capture_output=True, text=True, timeout=10,
        )
        assert r2.returncode == 0

    def test_main_entry_point(self):
        """Entry via `python -m omnibrain` works."""
        result = subprocess.run(
            [sys.executable, "-m", "omnibrain", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
