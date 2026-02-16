"""
Tests for Skill Runtime — discovery, manifest parsing, trigger matching,
handler invocation, and the main run loop.

Groups:
    ManifestParsing  — parsing skill.yaml
    ScheduleParsing  — converting schedule specs to seconds
    TriggerMatching  — on_ask regex, on_event exact match
    Discovery        — scanning directories for Skills
    HandlerLoading   — importing handler modules
    RuntimeInvoke    — match_ask, handle_event, tick
    EventBusWiring   — on_event triggers → event bus
    RuntimeLoop      — run/stop lifecycle
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from omnibrain.skill_context import EventBus
from omnibrain.skill_runtime import (
    SkillManifest,
    SkillRuntime,
    SkillTrigger,
    parse_manifest,
    parse_schedule,
    _load_handler,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _write_skill(tmp_path: Path, name: str, yaml_content: str, handlers: dict[str, str] | None = None) -> Path:
    """Create a minimal Skill directory with skill.yaml and optional handler files."""
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(textwrap.dedent(yaml_content))

    if handlers:
        handlers_dir = skill_dir / "handlers"
        handlers_dir.mkdir()
        for fname, code in handlers.items():
            (handlers_dir / fname).write_text(textwrap.dedent(code))

    return skill_dir


MINIMAL_YAML = """\
name: test-skill
version: 1.0.0
description: "A test skill"
author: tester
triggers:
  - on_ask: "hello|world"
permissions:
  - read_memory
  - notify
handlers:
  on_ask: "handlers/ask.py"
"""

SCHEDULE_YAML = """\
name: sched-skill
version: 1.0.0
description: "Scheduled skill"
triggers:
  - schedule: "every 5m"
permissions:
  - read_memory
handlers:
  schedule: "handlers/poll.py"
"""

EVENT_YAML = """\
name: event-skill
version: 1.0.0
description: "Event-driven skill"
triggers:
  - on_event: "new_email"
permissions:
  - read_memory
handlers:
  on_event: "handlers/event.py"
"""

ASK_HANDLER = """\
async def handle(ctx, message):
    return f"echo: {message}"
"""

SCHEDULE_HANDLER = """\
async def handle(ctx):
    ctx.log("tick")
"""

EVENT_HANDLER = """\
async def handle(ctx, event):
    ctx.log(f"event: {event}")
"""


# ═══════════════════════════════════════════════════════════════════════════
# Manifest Parsing
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestParsing:
    def test_parse_minimal(self, tmp_path):
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML)
        m = parse_manifest(tmp_path / "test-skill" / "skill.yaml")
        assert m is not None
        assert m.name == "test-skill"
        assert m.version == "1.0.0"
        assert len(m.triggers) == 1
        assert m.triggers[0].kind == "on_ask"
        assert m.triggers[0].value == "hello|world"
        assert "read_memory" in m.permissions
        assert m.handlers["on_ask"] == "handlers/ask.py"

    def test_parse_schedule(self, tmp_path):
        _write_skill(tmp_path, "sched-skill", SCHEDULE_YAML)
        m = parse_manifest(tmp_path / "sched-skill" / "skill.yaml")
        assert m is not None
        assert len(m.schedule_triggers) == 1
        assert m.schedule_triggers[0].value == "every 5m"

    def test_parse_event(self, tmp_path):
        _write_skill(tmp_path, "event-skill", EVENT_YAML)
        m = parse_manifest(tmp_path / "event-skill" / "skill.yaml")
        assert len(m.event_triggers) == 1
        assert m.event_triggers[0].value == "new_email"

    def test_parse_bad_yaml(self, tmp_path):
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text(": invalid: yaml: {{}")
        m = parse_manifest(skill_dir / "skill.yaml")
        assert m is None

    def test_parse_missing_name(self, tmp_path):
        skill_dir = tmp_path / "noname"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("version: 1.0.0\n")
        m = parse_manifest(skill_dir / "skill.yaml")
        assert m is None

    def test_parse_nonexistent(self, tmp_path):
        m = parse_manifest(tmp_path / "nope" / "skill.yaml")
        assert m is None

    def test_manifest_to_dict(self, tmp_path):
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML)
        m = parse_manifest(tmp_path / "test-skill" / "skill.yaml")
        d = m.to_dict()
        assert d["name"] == "test-skill"
        assert isinstance(d["triggers"], list)
        assert d["triggers"][0]["kind"] == "on_ask"

    def test_multi_trigger_yaml(self, tmp_path):
        yaml_ = """\
        name: multi
        version: 1.0.0
        triggers:
          - schedule: "every 1h"
          - on_ask: "check"
          - on_event: "tick"
        permissions: []
        handlers: {}
        """
        _write_skill(tmp_path, "multi", yaml_)
        m = parse_manifest(tmp_path / "multi" / "skill.yaml")
        assert len(m.triggers) == 3
        assert len(m.schedule_triggers) == 1
        assert len(m.ask_triggers) == 1
        assert len(m.event_triggers) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Schedule Parsing
# ═══════════════════════════════════════════════════════════════════════════


class TestScheduleParsing:
    def test_every_5m(self):
        assert parse_schedule("every 5m") == 300

    def test_every_1h(self):
        assert parse_schedule("every 1h") == 3600

    def test_every_6h(self):
        assert parse_schedule("every 6h") == 21600

    def test_every_15min(self):
        assert parse_schedule("every 15m") == 900

    def test_daily(self):
        assert parse_schedule("daily 7:00") == 86400

    def test_cron(self):
        assert parse_schedule("cron 0 7 * * *") == 86400

    def test_unknown(self):
        assert parse_schedule("random junk") == 0

    def test_case_insensitive(self):
        assert parse_schedule("Every 10M") == 600


# ═══════════════════════════════════════════════════════════════════════════
# Trigger Matching
# ═══════════════════════════════════════════════════════════════════════════


class TestTriggerMatching:
    def test_on_ask_match(self):
        t = SkillTrigger(kind="on_ask", value="email|inbox|mail")
        assert t.matches_ask("check my email") is True
        assert t.matches_ask("what's in my inbox") is True
        assert t.matches_ask("hello world") is False

    def test_on_ask_case_insensitive(self):
        t = SkillTrigger(kind="on_ask", value="email")
        assert t.matches_ask("CHECK EMAIL") is True

    def test_on_ask_wrong_kind(self):
        t = SkillTrigger(kind="schedule", value="every 5m")
        assert t.matches_ask("anything") is False

    def test_on_event_match(self):
        t = SkillTrigger(kind="on_event", value="new_email")
        assert t.matches_event("new_email") is True
        assert t.matches_event("calendar_update") is False

    def test_on_event_wrong_kind(self):
        t = SkillTrigger(kind="on_ask", value="email")
        assert t.matches_event("email") is False

    def test_bad_regex_no_crash(self):
        t = SkillTrigger(kind="on_ask", value="[invalid")
        assert t.matches_ask("test") is False


# ═══════════════════════════════════════════════════════════════════════════
# Discovery
# ═══════════════════════════════════════════════════════════════════════════


class TestDiscovery:
    def test_discover_skills(self, tmp_path):
        _write_skill(tmp_path, "skill-a", MINIMAL_YAML.replace("test-skill", "skill-a"))
        _write_skill(tmp_path, "skill-b", SCHEDULE_YAML)
        rt = SkillRuntime()
        found = rt.discover([tmp_path])
        assert len(found) == 2
        assert "skill-a" in rt.skills
        assert "sched-skill" in rt.skills

    def test_discover_empty_dir(self, tmp_path):
        rt = SkillRuntime()
        found = rt.discover([tmp_path])
        assert found == []

    def test_discover_nonexistent(self, tmp_path):
        rt = SkillRuntime()
        found = rt.discover([tmp_path / "nope"])
        assert found == []

    def test_discover_deduplicates(self, tmp_path):
        """Same skill name discovered twice → only first wins."""
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML)
        rt = SkillRuntime()
        rt.discover([tmp_path])
        rt.discover([tmp_path])  # second scan
        assert len(rt.skills) == 1

    def test_discover_skips_bad_manifest(self, tmp_path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("not_valid: true\n")
        _write_skill(tmp_path, "good-skill", MINIMAL_YAML.replace("test-skill", "good-skill"))
        rt = SkillRuntime()
        found = rt.discover([tmp_path])
        assert len(found) == 1
        assert found[0].name == "good-skill"


# ═══════════════════════════════════════════════════════════════════════════
# Handler Loading
# ═══════════════════════════════════════════════════════════════════════════


class TestHandlerLoading:
    def test_load_valid_handler(self, tmp_path):
        _write_skill(tmp_path, "s", MINIMAL_YAML, {"ask.py": ASK_HANDLER})
        fn = _load_handler(tmp_path / "s", "handlers/ask.py")
        assert fn is not None
        assert asyncio.iscoroutinefunction(fn)

    def test_load_missing_handler(self, tmp_path):
        fn = _load_handler(tmp_path, "handlers/nonexistent.py")
        assert fn is None

    def test_load_handler_no_handle_fn(self, tmp_path):
        _write_skill(tmp_path, "s", MINIMAL_YAML, {"ask.py": "x = 1\n"})
        fn = _load_handler(tmp_path / "s", "handlers/ask.py")
        assert fn is None


# ═══════════════════════════════════════════════════════════════════════════
# Runtime — match_ask
# ═══════════════════════════════════════════════════════════════════════════


class TestMatchAsk:
    @pytest.mark.asyncio
    async def test_match_ask_invokes_handler(self, tmp_path):
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML, {"ask.py": ASK_HANDLER})
        rt = SkillRuntime()
        rt.discover([tmp_path])

        results = await rt.match_ask("hello there")
        assert len(results) == 1
        assert results[0]["skill"] == "test-skill"
        assert results[0]["result"] == "echo: hello there"

    @pytest.mark.asyncio
    async def test_no_match(self, tmp_path):
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML, {"ask.py": ASK_HANDLER})
        rt = SkillRuntime()
        rt.discover([tmp_path])

        results = await rt.match_ask("unrelated query about weather")
        assert results == []

    @pytest.mark.asyncio
    async def test_disabled_skill_skipped(self, tmp_path):
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML, {"ask.py": ASK_HANDLER})
        rt = SkillRuntime()
        rt.discover([tmp_path])
        rt._skills["test-skill"].enabled = False

        results = await rt.match_ask("hello")
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════
# Runtime — handle_event
# ═══════════════════════════════════════════════════════════════════════════


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_handle_matching_event(self, tmp_path):
        _write_skill(tmp_path, "event-skill", EVENT_YAML, {"event.py": EVENT_HANDLER})
        rt = SkillRuntime()
        rt.discover([tmp_path])

        count = await rt.handle_event("new_email", {"subject": "test"})
        assert count == 1

    @pytest.mark.asyncio
    async def test_handle_non_matching_event(self, tmp_path):
        _write_skill(tmp_path, "event-skill", EVENT_YAML, {"event.py": EVENT_HANDLER})
        rt = SkillRuntime()
        rt.discover([tmp_path])

        count = await rt.handle_event("unknown_event", {})
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════
# Runtime — tick (schedule)
# ═══════════════════════════════════════════════════════════════════════════


class TestTick:
    @pytest.mark.asyncio
    async def test_tick_invokes_due_handler(self, tmp_path):
        _write_skill(tmp_path, "sched-skill", SCHEDULE_YAML, {"poll.py": SCHEDULE_HANDLER})
        rt = SkillRuntime()
        rt.discover([tmp_path])

        count = await rt.tick()
        assert count == 1  # First tick always runs (last_run = 0)

    @pytest.mark.asyncio
    async def test_tick_respects_interval(self, tmp_path):
        _write_skill(tmp_path, "sched-skill", SCHEDULE_YAML, {"poll.py": SCHEDULE_HANDLER})
        rt = SkillRuntime()
        rt.discover([tmp_path])

        await rt.tick()  # first run
        count = await rt.tick()  # immediately after → too soon
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════
# Runtime — event bus wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestEventBusWiring:
    @pytest.mark.asyncio
    async def test_on_event_triggers_wired_to_bus(self, tmp_path):
        _write_skill(tmp_path, "event-skill", EVENT_YAML, {"event.py": EVENT_HANDLER})
        bus = EventBus()
        rt = SkillRuntime(event_bus=bus)
        rt.discover([tmp_path])

        # Verify bus listener is registered for "new_email"
        assert "new_email" in bus._listeners
        assert len(bus._listeners["new_email"]) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Runtime — run/stop
# ═══════════════════════════════════════════════════════════════════════════


class TestRuntimeLifecycle:
    @pytest.mark.asyncio
    async def test_run_and_stop(self, tmp_path):
        rt = SkillRuntime()

        async def stop_after_short_delay():
            await asyncio.sleep(0.1)
            await rt.stop()

        task = asyncio.create_task(stop_after_short_delay())
        await rt.run()
        await task
        assert rt._running is False

    def test_get_status(self, tmp_path):
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML)
        rt = SkillRuntime()
        rt.discover([tmp_path])
        status = rt.get_status()
        assert status["skill_count"] == 1
        assert "test-skill" in status["skills"]

    def test_list_skills(self, tmp_path):
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML)
        rt = SkillRuntime()
        rt.discover([tmp_path])
        lst = rt.list_skills()
        assert len(lst) == 1
        assert lst[0]["name"] == "test-skill"


# ═══════════════════════════════════════════════════════════════════════════
# Handler error resilience
# ═══════════════════════════════════════════════════════════════════════════


class TestHandlerErrors:
    @pytest.mark.asyncio
    async def test_failing_handler_returns_none(self, tmp_path):
        bad_handler = """\
async def handle(ctx, message):
    raise RuntimeError("boom")
"""
        _write_skill(tmp_path, "test-skill", MINIMAL_YAML, {"ask.py": bad_handler})
        rt = SkillRuntime()
        rt.discover([tmp_path])

        results = await rt.match_ask("hello")
        assert len(results) == 1
        assert results[0]["result"] is None  # Error → None, not crash


# ═══════════════════════════════════════════════════════════════════════════
# DB installed_skills integration
# ═══════════════════════════════════════════════════════════════════════════


class TestDBInstalledSkills:
    def test_install_and_list(self, tmp_path):
        from omnibrain.db import OmniBrainDB
        db = OmniBrainDB(tmp_path)
        db.install_skill("email-manager", "1.0.0", "Email skill", "francesco")
        skills = db.get_installed_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "email-manager"

    def test_remove_skill(self, tmp_path):
        from omnibrain.db import OmniBrainDB
        db = OmniBrainDB(tmp_path)
        db.install_skill("test", "1.0.0")
        assert db.remove_skill("test") is True
        assert db.get_installed_skills() == []

    def test_remove_nonexistent(self, tmp_path):
        from omnibrain.db import OmniBrainDB
        db = OmniBrainDB(tmp_path)
        assert db.remove_skill("nope") is False

    def test_enable_disable(self, tmp_path):
        from omnibrain.db import OmniBrainDB
        db = OmniBrainDB(tmp_path)
        db.install_skill("s", "1.0.0")
        db.set_skill_enabled("s", False)
        skills = db.get_installed_skills(enabled_only=True)
        assert len(skills) == 0
        db.set_skill_enabled("s", True)
        skills = db.get_installed_skills(enabled_only=True)
        assert len(skills) == 1

    def test_skill_data(self, tmp_path):
        from omnibrain.db import OmniBrainDB
        db = OmniBrainDB(tmp_path)
        db.install_skill("s", "1.0.0")
        db.set_skill_data("s", {"last_poll": "2026-02-16"})
        data = db.get_skill_data("s")
        assert data["last_poll"] == "2026-02-16"

    def test_get_installed_skill(self, tmp_path):
        from omnibrain.db import OmniBrainDB
        db = OmniBrainDB(tmp_path)
        db.install_skill("s", "1.0.0", description="test", author="me")
        row = db.get_installed_skill("s")
        assert row is not None
        assert row["author"] == "me"

    def test_upsert_on_reinstall(self, tmp_path):
        from omnibrain.db import OmniBrainDB
        db = OmniBrainDB(tmp_path)
        db.install_skill("s", "1.0.0", description="old")
        db.install_skill("s", "2.0.0", description="new")
        row = db.get_installed_skill("s")
        assert row["version"] == "2.0.0"

    def test_stats_includes_skills(self, tmp_path):
        from omnibrain.db import OmniBrainDB
        db = OmniBrainDB(tmp_path)
        db.install_skill("s", "1.0.0")
        stats = db.get_stats()
        assert stats["installed_skills"] == 1
