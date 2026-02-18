"""
Tests for Skill Sandbox — subprocess isolation, JSON-RPC bridge,
permission enforcement, venv management, and SkillContextProxy.

Groups:
    Bridge          — SkillSandboxBridge RPC handling + permission enforcement
    VenvManagement  — ensure_skill_venv creation and caching
    ContextProxy    — SkillContextProxy serialization
    Integration     — End-to-end sandboxed handler invocation
"""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnibrain.skill_sandbox import (
    ALLOWED_METHODS,
    RPC_GET_EVENTS,
    RPC_GET_PREFERENCE,
    RPC_LOG,
    RPC_LLM_COMPLETE,
    RPC_MEMORY_SEARCH,
    RPC_MEMORY_STORE,
    RPC_NOTIFY,
    RPC_PROPOSE,
    SkillContextProxy,
    SkillSandboxBridge,
    ensure_skill_venv,
    _hash_deps,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_bridge(**kwargs) -> SkillSandboxBridge:
    """Create a bridge with reasonable defaults."""
    defaults = {
        "skill_name": "test-skill",
        "permissions": {"read_memory", "notify", "llm_access"},
    }
    defaults.update(kwargs)
    return SkillSandboxBridge(**defaults)


def _make_rpc(method: str, params: dict = None, req_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Bridge — Permission Enforcement
# ═══════════════════════════════════════════════════════════════════════════


class TestBridgePermissions:
    def test_log_always_allowed(self):
        bridge = _make_bridge(permissions=set())
        assert bridge.check_permission(RPC_LOG) is True

    def test_memory_search_needs_read_memory(self):
        bridge = _make_bridge(permissions={"notify"})
        assert bridge.check_permission(RPC_MEMORY_SEARCH) is False

        bridge2 = _make_bridge(permissions={"read_memory"})
        assert bridge2.check_permission(RPC_MEMORY_SEARCH) is True

    def test_memory_store_needs_write_memory(self):
        bridge = _make_bridge(permissions={"read_memory"})
        assert bridge.check_permission(RPC_MEMORY_STORE) is False

        bridge2 = _make_bridge(permissions={"write_memory"})
        assert bridge2.check_permission(RPC_MEMORY_STORE) is True

    def test_notify_needs_notify(self):
        bridge = _make_bridge(permissions=set())
        assert bridge.check_permission(RPC_NOTIFY) is False

    def test_llm_needs_llm_access(self):
        bridge = _make_bridge(permissions={"llm_access"})
        assert bridge.check_permission(RPC_LLM_COMPLETE) is True

    def test_all_methods_have_permission_mapping(self):
        """Every allowed RPC method must have a permission mapping."""
        for method in ALLOWED_METHODS:
            assert method in SkillSandboxBridge.PERMISSION_MAP


class TestBridgeRPC:
    @pytest.mark.asyncio
    async def test_permission_denied_returns_error(self):
        bridge = _make_bridge(permissions=set())  # no permissions
        resp = await bridge.handle_rpc(_make_rpc(RPC_MEMORY_SEARCH, {"query": "test"}))
        assert "error" in resp
        assert resp["error"]["code"] == -32001
        assert "Permission denied" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_rate_limit(self):
        bridge = _make_bridge()
        bridge._max_calls_per_invocation = 2

        # First two calls pass
        resp1 = await bridge.handle_rpc(_make_rpc(RPC_LOG, {"message": "a"}, 1))
        assert "result" in resp1
        resp2 = await bridge.handle_rpc(_make_rpc(RPC_LOG, {"message": "b"}, 2))
        assert "result" in resp2

        # Third call hits rate limit
        resp3 = await bridge.handle_rpc(_make_rpc(RPC_LOG, {"message": "c"}, 3))
        assert "error" in resp3
        assert resp3["error"]["code"] == -32000
        assert "Rate limit" in resp3["error"]["message"]

    @pytest.mark.asyncio
    async def test_memory_search_dispatch(self):
        mock_mem = MagicMock()
        result_item = MagicMock(text="found it", source="test", score=0.95)
        mock_mem.search.return_value = [result_item]

        bridge = _make_bridge(permissions={"read_memory"}, memory=mock_mem)
        resp = await bridge.handle_rpc(
            _make_rpc(RPC_MEMORY_SEARCH, {"query": "hello", "max_results": 5})
        )
        assert "result" in resp
        assert len(resp["result"]) == 1
        assert resp["result"][0]["text"] == "found it"
        mock_mem.search.assert_called_once_with("hello", max_results=5)

    @pytest.mark.asyncio
    async def test_memory_store_dispatch(self):
        mock_mem = MagicMock()
        bridge = _make_bridge(permissions={"write_memory"}, memory=mock_mem)
        resp = await bridge.handle_rpc(
            _make_rpc(RPC_MEMORY_STORE, {"text": "important", "source_type": "note"})
        )
        assert resp["result"] is True
        mock_mem.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_dispatch(self):
        mock_bus = MagicMock()
        bridge = _make_bridge(permissions={"notify"}, event_bus=mock_bus)
        resp = await bridge.handle_rpc(
            _make_rpc(RPC_NOTIFY, {
                "title": "Alert",
                "message": "Something happened",
                "level": "important",
            })
        )
        assert resp["result"] is True
        mock_bus.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_dispatch(self):
        bridge = _make_bridge()
        resp = await bridge.handle_rpc(
            _make_rpc(RPC_LOG, {"message": "test log", "level": "info"})
        )
        assert resp["result"] is True

    @pytest.mark.asyncio
    async def test_get_preference_dispatch(self):
        mock_db = MagicMock()
        mock_db.get_preference.return_value = "dark"
        bridge = _make_bridge(permissions={"read_preferences"}, db=mock_db)
        resp = await bridge.handle_rpc(
            _make_rpc(RPC_GET_PREFERENCE, {"key": "theme"})
        )
        assert resp["result"] == "dark"

    @pytest.mark.asyncio
    async def test_propose_action_dispatch(self):
        mock_db = MagicMock()
        bridge = _make_bridge(permissions={"propose_actions"}, db=mock_db)
        resp = await bridge.handle_rpc(
            _make_rpc(RPC_PROPOSE, {
                "title": "Send report",
                "description": "Weekly summary",
                "priority": 3,
            })
        )
        assert resp["result"] is True
        mock_db.create_proposal.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_exception_returns_error(self):
        mock_mem = MagicMock()
        mock_mem.search.side_effect = RuntimeError("DB crashed")
        bridge = _make_bridge(permissions={"read_memory"}, memory=mock_mem)
        resp = await bridge.handle_rpc(
            _make_rpc(RPC_MEMORY_SEARCH, {"query": "test"})
        )
        assert "error" in resp
        assert resp["error"]["code"] == -32603
        assert "DB crashed" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_no_backend_returns_empty(self):
        """If no memory/db is wired, gracefully return empty."""
        bridge = _make_bridge(permissions={"read_memory"})
        resp = await bridge.handle_rpc(_make_rpc(RPC_MEMORY_SEARCH, {"query": "x"}))
        assert resp["result"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Venv Management
# ═══════════════════════════════════════════════════════════════════════════


class TestVenvManagement:
    def test_no_deps_returns_sys_executable(self, tmp_path):
        result = ensure_skill_venv(tmp_path, [])
        assert result == sys.executable

    def test_hash_deps_deterministic(self):
        h1 = _hash_deps(["requests", "beautifulsoup4"])
        h2 = _hash_deps(["requests", "beautifulsoup4"])
        assert h1 == h2

    def test_hash_deps_order_independent(self):
        h1 = _hash_deps(["requests", "beautifulsoup4"])
        h2 = _hash_deps(["beautifulsoup4", "requests"])
        assert h1 == h2  # sorted internally

    def test_hash_deps_different(self):
        h1 = _hash_deps(["requests"])
        h2 = _hash_deps(["httpx"])
        assert h1 != h2

    def test_cached_venv_reused(self, tmp_path):
        """If venv + marker exist and match, we skip creation."""
        skill_path = tmp_path / "test-skill"
        skill_path.mkdir()
        venv_path = skill_path / ".venv" / "bin"
        venv_path.mkdir(parents=True)

        # Create a fake python
        fake_python = venv_path / "python"
        fake_python.write_text("#!/bin/sh\necho fake")
        fake_python.chmod(0o755)

        # Write matching marker
        deps = ["requests"]
        marker = skill_path / ".venv" / ".deps_installed"
        marker.write_text(_hash_deps(deps))

        result = ensure_skill_venv(skill_path, deps)
        assert result == str(fake_python)


# ═══════════════════════════════════════════════════════════════════════════
# SkillContextProxy
# ═══════════════════════════════════════════════════════════════════════════


class TestSkillContextProxy:
    def test_proxy_init(self):
        proxy = SkillContextProxy("my-skill")
        assert proxy.skill_name == "my-skill"
        assert proxy._request_id == 0

    def test_send_rpc_increments_id(self):
        """Verify that _send_rpc produces incrementing request IDs."""
        proxy = SkillContextProxy("test")

        response1 = json.dumps({"id": 1, "result": [{"text": "hi"}]}) + "\n"
        response2 = json.dumps({"id": 2, "result": True}) + "\n"

        captured = []
        call_count = 0

        def mock_write(data):
            captured.append(data)

        def mock_readline():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return response1
            return response2

        with patch.object(sys, "stdout", wraps=sys.stdout) as mock_stdout, \
             patch.object(sys, "stdin", wraps=sys.stdin) as mock_stdin:
            mock_stdout.write = mock_write
            mock_stdout.flush = MagicMock()
            mock_stdin.readline = mock_readline

            result1 = proxy._send_rpc(RPC_MEMORY_SEARCH, {"query": "test"})
            result2 = proxy._send_rpc(RPC_LOG, {"message": "hello"})

        assert proxy._request_id == 2
        assert result1 == [{"text": "hi"}]
        assert result2 is True

        # Parse captured writes — each _send_rpc does one write (json + newline)
        requests_sent = [
            json.loads(s) for s in captured if s.strip() and s.strip().startswith("{")
        ]
        assert len(requests_sent) == 2
        assert requests_sent[0]["id"] == 1
        assert requests_sent[0]["method"] == RPC_MEMORY_SEARCH
        assert requests_sent[1]["id"] == 2
        assert requests_sent[1]["method"] == RPC_LOG

    def test_send_rpc_error_raises(self):
        """Verify that RPC errors are raised as RuntimeError."""
        proxy = SkillContextProxy("test")

        error_response = json.dumps({
            "id": 1,
            "error": {"code": -32001, "message": "Permission denied"},
        }) + "\n"

        with patch.object(sys, "stdout", wraps=sys.stdout) as mock_stdout, \
             patch.object(sys, "stdin", wraps=sys.stdin) as mock_stdin:
            mock_stdout.write = MagicMock()
            mock_stdout.flush = MagicMock()
            mock_stdin.readline = MagicMock(return_value=error_response)

            with pytest.raises(RuntimeError, match="Permission denied"):
                proxy._send_rpc(RPC_MEMORY_SEARCH, {"query": "x"})


# ═══════════════════════════════════════════════════════════════════════════
# Integration — Sandboxed SkillRuntime
# ═══════════════════════════════════════════════════════════════════════════


def _write_skill(
    tmp_path: Path,
    name: str,
    yaml_content: str,
    handlers: dict[str, str] | None = None,
) -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(textwrap.dedent(yaml_content))

    if handlers:
        handlers_dir = skill_dir / "handlers"
        handlers_dir.mkdir()
        for fname, code in handlers.items():
            (handlers_dir / fname).write_text(textwrap.dedent(code))

    return skill_dir


class TestRuntimeSandboxFlag:
    """Verify that sandbox_enabled controls execution path."""

    def test_default_sandbox_off(self):
        from omnibrain.skill_runtime import SkillRuntime
        rt = SkillRuntime()
        assert rt._sandbox_enabled is False

    def test_sandbox_on(self):
        from omnibrain.skill_runtime import SkillRuntime
        rt = SkillRuntime(sandbox_enabled=True)
        assert rt._sandbox_enabled is True

    @pytest.mark.asyncio
    async def test_direct_invocation_without_sandbox(self, tmp_path):
        from omnibrain.skill_runtime import SkillRuntime

        YAML = """\
        name: echo-skill
        version: 1.0.0
        triggers:
          - on_ask: "echo"
        permissions:
          - read_memory
        handlers:
          on_ask: "handlers/ask.py"
        """
        HANDLER = """\
        async def handle(ctx, message):
            return f"echo: {message}"
        """
        _write_skill(tmp_path, "echo-skill", YAML, {"ask.py": HANDLER})
        rt = SkillRuntime(sandbox_enabled=False)
        rt.discover([tmp_path])

        results = await rt.match_ask("echo test")
        assert len(results) == 1
        assert results[0]["result"] == "echo: echo test"

    @pytest.mark.asyncio
    async def test_sandbox_calls_sandboxed_invoke(self, tmp_path):
        """When sandbox is on, _invoke_handler delegates to _invoke_handler_sandboxed."""
        from omnibrain.skill_runtime import SkillRuntime, SkillManifest

        YAML = """\
        name: test-sk
        version: 1.0.0
        triggers:
          - on_ask: "test"
        permissions: []
        handlers:
          on_ask: "handlers/ask.py"
        """
        HANDLER = """\
        async def handle(ctx, msg):
            return "result"
        """
        _write_skill(tmp_path, "test-sk", YAML, {"ask.py": HANDLER})
        rt = SkillRuntime(sandbox_enabled=True)
        rt.discover([tmp_path])

        # Mock the sandboxed method to verify it's called
        rt._invoke_handler_sandboxed = AsyncMock(return_value="sandboxed_result")

        manifest = rt._skills["test-sk"]
        result = await rt._invoke_handler(manifest, "on_ask", "test")
        rt._invoke_handler_sandboxed.assert_called_once()
        assert result == "sandboxed_result"


class TestVenvOnDiscovery:
    def test_deps_trigger_venv_setup(self, tmp_path):
        from omnibrain.skill_runtime import SkillRuntime

        YAML = """\
        name: dep-skill
        version: 1.0.0
        triggers: []
        permissions: []
        handlers: {}
        dependencies:
          - requests
        """
        _write_skill(tmp_path, "dep-skill", YAML)
        rt = SkillRuntime()

        with patch("omnibrain.skill_sandbox.ensure_skill_venv", return_value="/fake/python") as mock_venv:
            rt.discover([tmp_path])
            mock_venv.assert_called_once()
            assert rt._skill_python["dep-skill"] == "/fake/python"

    def test_no_deps_no_venv(self, tmp_path):
        from omnibrain.skill_runtime import SkillRuntime

        YAML = """\
        name: simple-skill
        version: 1.0.0
        triggers: []
        permissions: []
        handlers: {}
        """
        _write_skill(tmp_path, "simple-skill", YAML)
        rt = SkillRuntime()

        with patch("omnibrain.skill_sandbox.ensure_skill_venv") as mock_venv:
            rt.discover([tmp_path])
            mock_venv.assert_not_called()
