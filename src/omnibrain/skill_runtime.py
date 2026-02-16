"""
OmniBrain — Skill Runtime

Loads Skills from disk, registers triggers, invokes handlers in sandboxed
``SkillContext`` instances.

Responsibilities:
    1. Discover ``skill.yaml`` manifests in skill directories
    2. Parse manifests into ``SkillManifest`` dataclasses
    3. Register schedule / on_ask / on_event triggers
    4. On trigger match → create ``SkillContext`` → call handler
    5. Track installed/enabled state via DB

Directory resolution (in order):
    - ``<project>/skills/``       built-in Skills
    - ``~/.omnibrain/skills/``    user-installed Skills

The Runtime is designed as an asyncio-friendly component that the daemon
starts as a long-lived coroutine via ``runtime.run()``.
"""

from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from omnibrain.skill_context import EventBus, SkillContext

logger = logging.getLogger("omnibrain.skill_runtime")


# ─── Data classes ─────────────────────────────────────────────────────────


@dataclass
class SkillTrigger:
    """A single trigger from a Skill manifest."""

    kind: str  # "schedule" | "on_ask" | "on_event"
    value: str  # cron-like string | regex pattern | event type
    _compiled_re: Any = field(default=None, repr=False, compare=False)

    def matches_ask(self, user_message: str) -> bool:
        """Return True if *user_message* matches this on_ask regex."""
        if self.kind != "on_ask":
            return False
        if self._compiled_re is None:
            try:
                self._compiled_re = re.compile(self.value, re.IGNORECASE)
            except re.error:
                logger.warning(f"Invalid on_ask regex: {self.value}")
                return False
        return bool(self._compiled_re.search(user_message))

    def matches_event(self, event_type: str) -> bool:
        """Return True if *event_type* matches this on_event trigger."""
        if self.kind != "on_event":
            return False
        return self.value == event_type


@dataclass
class SkillManifest:
    """Parsed ``skill.yaml`` manifest."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    icon: str = ""
    category: str = "other"

    triggers: list[SkillTrigger] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    handlers: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    requires_core: str = ""

    path: Path = field(default_factory=lambda: Path("."))
    enabled: bool = True

    # ── Helpers ──

    @property
    def schedule_triggers(self) -> list[SkillTrigger]:
        return [t for t in self.triggers if t.kind == "schedule"]

    @property
    def ask_triggers(self) -> list[SkillTrigger]:
        return [t for t in self.triggers if t.kind == "on_ask"]

    @property
    def event_triggers(self) -> list[SkillTrigger]:
        return [t for t in self.triggers if t.kind == "on_event"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "category": self.category,
            "icon": self.icon,
            "permissions": self.permissions,
            "triggers": [
                {"kind": t.kind, "value": t.value} for t in self.triggers
            ],
            "handlers": self.handlers,
            "enabled": self.enabled,
            "path": str(self.path),
        }


# ─── Manifest parser ─────────────────────────────────────────────────────


def parse_manifest(yaml_path: Path) -> SkillManifest | None:
    """Parse a ``skill.yaml`` file into a ``SkillManifest``.

    Returns ``None`` on validation failure (logs a warning).
    """
    try:
        raw = yaml.safe_load(yaml_path.read_text())
    except Exception as e:
        logger.warning(f"Cannot read {yaml_path}: {e}")
        return None

    if not isinstance(raw, dict):
        logger.warning(f"Invalid skill.yaml (not a dict): {yaml_path}")
        return None

    name = raw.get("name")
    if not name or not isinstance(name, str):
        logger.warning(f"skill.yaml missing 'name': {yaml_path}")
        return None

    # ── Triggers ──
    triggers: list[SkillTrigger] = []
    for t in raw.get("triggers", []):
        if isinstance(t, dict):
            for kind in ("schedule", "on_ask", "on_event"):
                if kind in t:
                    triggers.append(SkillTrigger(kind=kind, value=str(t[kind])))

    # ── Handlers ──
    handlers: dict[str, str] = {}
    raw_handlers = raw.get("handlers", {})
    if isinstance(raw_handlers, dict):
        for key, val in raw_handlers.items():
            handlers[key] = str(val)

    return SkillManifest(
        name=name,
        version=str(raw.get("version", "0.1.0")),
        description=raw.get("description", ""),
        author=raw.get("author", ""),
        homepage=raw.get("homepage", ""),
        icon=raw.get("icon", ""),
        category=raw.get("category", "other"),
        triggers=triggers,
        permissions=list(raw.get("permissions", [])),
        settings=raw.get("settings", {}),
        handlers=handlers,
        dependencies=list(raw.get("dependencies", [])),
        requires_core=str(raw.get("requires_core", "")),
        path=yaml_path.parent,
        enabled=True,
    )


# ─── Schedule parsing ─────────────────────────────────────────────────────


def parse_schedule(spec: str) -> int:
    """Convert a schedule spec like ``"every 5m"`` to seconds.

    Supported formats:
        ``"every 5m"``   → 300
        ``"every 1h"``   → 3600
        ``"every 6h"``   → 21600
        ``"cron 0 7 * * *"`` → 86400 (daily)
        ``"daily 7:00"``     → 86400

    Returns 0 if the spec is unrecognised (caller should skip).
    """
    spec = spec.strip().lower()

    # "every Nm" / "every Nh"
    m = re.match(r"every\s+(\d+)\s*m(?:in(?:ute)?s?)?$", spec)
    if m:
        return int(m.group(1)) * 60

    m = re.match(r"every\s+(\d+)\s*h(?:ours?)?$", spec)
    if m:
        return int(m.group(1)) * 3600

    # "daily HH:MM" → treat as once per day
    if spec.startswith("daily") or spec.startswith("cron"):
        return 86400

    return 0


# ─── Handler loader ───────────────────────────────────────────────────────


def _load_handler(skill_path: Path, handler_relpath: str) -> Any:
    """Import a handler module and return its ``handle`` function.

    Returns ``None`` on failure.
    """
    handler_file = skill_path / handler_relpath
    if not handler_file.exists():
        logger.warning(f"Handler not found: {handler_file}")
        return None

    module_name = f"skill_handler_{skill_path.name}_{handler_file.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, handler_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            handle_fn = getattr(module, "handle", None)
            if handle_fn is None:
                logger.warning(f"Handler {handler_file} has no 'handle' function")
            return handle_fn
    except Exception as e:
        logger.error(f"Failed to load handler {handler_file}: {e}")
    return None


# ─── Skill Runtime ────────────────────────────────────────────────────────


class SkillRuntime:
    """Loads Skills, matches triggers, invokes handlers.

    Usage::

        runtime = SkillRuntime(db=db, memory=mm, event_bus=bus)
        runtime.discover([project_skills_dir, user_skills_dir])
        await runtime.run()          # long-lived loop
        results = await runtime.match_ask("check my email")
    """

    def __init__(
        self,
        *,
        db: Any = None,
        memory: Any = None,
        knowledge_graph: Any = None,
        approval_gate: Any = None,
        config: Any = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = db
        self._memory = memory
        self._kg = knowledge_graph
        self._approval = approval_gate
        self._config = config
        self._event_bus = event_bus or EventBus()

        self._skills: dict[str, SkillManifest] = {}  # name → manifest
        self._handlers_cache: dict[str, Any] = {}  # "name:handler_key" → fn
        self._running = False

        # Schedule tracking: skill_name → {trigger_value: last_run_ts}
        self._schedule_last_run: dict[str, dict[str, float]] = {}

    # ──────────────────────────────────────────────────────────
    # Discovery
    # ──────────────────────────────────────────────────────────

    def discover(self, dirs: list[Path]) -> list[SkillManifest]:
        """Scan *dirs* for ``skill.yaml`` files and register manifests.

        Returns the list of newly discovered manifests.
        """
        found: list[SkillManifest] = []
        for d in dirs:
            if not d.is_dir():
                continue
            for child in sorted(d.iterdir()):
                yaml_path = child / "skill.yaml"
                if yaml_path.is_file():
                    manifest = parse_manifest(yaml_path)
                    if manifest and manifest.name not in self._skills:
                        self._skills[manifest.name] = manifest
                        found.append(manifest)
                        logger.info(
                            f"Discovered Skill: {manifest.name} v{manifest.version} "
                            f"({len(manifest.triggers)} triggers)"
                        )

        # Wire on_event triggers to the event bus
        for manifest in found:
            for trigger in manifest.event_triggers:
                self._event_bus.subscribe(
                    trigger.value,
                    self._make_event_callback(manifest, trigger),
                )

        return found

    @property
    def skills(self) -> dict[str, SkillManifest]:
        """All registered Skills keyed by name."""
        return dict(self._skills)

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    # ──────────────────────────────────────────────────────────
    # Context factory
    # ──────────────────────────────────────────────────────────

    def _make_context(self, manifest: SkillManifest) -> SkillContext:
        """Create a SkillContext for *manifest* with its declared permissions."""
        return SkillContext(
            skill_name=manifest.name,
            permissions=set(manifest.permissions),
            db=self._db,
            memory=self._memory,
            knowledge_graph=self._kg,
            approval_gate=self._approval,
            config=self._config,
            event_bus=self._event_bus,
        )

    # ──────────────────────────────────────────────────────────
    # Handler resolution + invocation
    # ──────────────────────────────────────────────────────────

    def _resolve_handler(self, manifest: SkillManifest, handler_key: str) -> Any:
        """Resolve and cache a handler function.

        *handler_key* is one of ``"schedule"``, ``"on_ask"``, ``"on_event"``.
        """
        cache_key = f"{manifest.name}:{handler_key}"
        if cache_key in self._handlers_cache:
            return self._handlers_cache[cache_key]

        relpath = manifest.handlers.get(handler_key)
        if not relpath:
            return None

        fn = _load_handler(manifest.path, relpath)
        if fn:
            self._handlers_cache[cache_key] = fn
        return fn

    async def _invoke_handler(
        self,
        manifest: SkillManifest,
        handler_key: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Resolve *handler_key*, create a ``SkillContext``, and call the handler."""
        fn = self._resolve_handler(manifest, handler_key)
        if fn is None:
            return None

        ctx = self._make_context(manifest)
        try:
            result = await fn(ctx, *args, **kwargs)
            logger.info(f"Skill '{manifest.name}' handler '{handler_key}' completed")
            return result
        except Exception as e:
            logger.error(
                f"Skill '{manifest.name}' handler '{handler_key}' failed: {e}"
            )
            return None

    # ──────────────────────────────────────────────────────────
    # Public trigger APIs
    # ──────────────────────────────────────────────────────────

    async def match_ask(self, user_message: str) -> list[dict[str, Any]]:
        """Match *user_message* against all on_ask triggers.

        Returns list of ``{"skill": name, "result": handler_return}``.
        Invokes every matching Skill's ``on_ask`` handler.
        """
        results: list[dict[str, Any]] = []
        for manifest in self._skills.values():
            if not manifest.enabled:
                continue
            for trigger in manifest.ask_triggers:
                if trigger.matches_ask(user_message):
                    result = await self._invoke_handler(
                        manifest, "on_ask", user_message
                    )
                    results.append({
                        "skill": manifest.name,
                        "result": result,
                    })
                    break  # one match per Skill is enough
        return results

    async def handle_event(self, event_type: str, data: dict[str, Any]) -> int:
        """Dispatch *event_type* to matching on_event handlers.

        Returns the number of Skills that handled the event.
        """
        count = 0
        for manifest in self._skills.values():
            if not manifest.enabled:
                continue
            for trigger in manifest.event_triggers:
                if trigger.matches_event(event_type):
                    await self._invoke_handler(
                        manifest, "on_event", data
                    )
                    count += 1
                    break
        return count

    async def tick(self) -> int:
        """Check all schedule triggers and invoke due handlers.

        Returns the number of handlers invoked.
        """
        import time

        now = time.time()
        invoked = 0

        for manifest in self._skills.values():
            if not manifest.enabled:
                continue

            skill_schedule = self._schedule_last_run.setdefault(manifest.name, {})

            for trigger in manifest.schedule_triggers:
                interval = parse_schedule(trigger.value)
                if interval <= 0:
                    continue

                last = skill_schedule.get(trigger.value, 0.0)
                if now - last >= interval:
                    await self._invoke_handler(manifest, "schedule")
                    skill_schedule[trigger.value] = now
                    invoked += 1

        return invoked

    async def run(self) -> None:
        """Long-lived loop: call ``tick()`` every 30 seconds."""
        import asyncio

        self._running = True
        logger.info(
            f"SkillRuntime started — {len(self._skills)} skills loaded"
        )

        while self._running:
            try:
                await self.tick()
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SkillRuntime tick error: {e}")
                await asyncio.sleep(30)

        logger.info("SkillRuntime stopped")

    async def stop(self) -> None:
        self._running = False

    # ──────────────────────────────────────────────────────────
    # Internal: event bus callback factory
    # ──────────────────────────────────────────────────────────

    def _make_event_callback(self, manifest: SkillManifest, trigger: SkillTrigger):
        """Return an async callback suitable for ``EventBus.subscribe``."""

        async def _cb(event_type: str, data: dict[str, Any]) -> None:
            await self._invoke_handler(manifest, "on_event", data)

        return _cb

    # ──────────────────────────────────────────────────────────
    # Info / status
    # ──────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "skill_count": len(self._skills),
            "skills": {
                name: m.to_dict() for name, m in self._skills.items()
            },
        }

    def list_skills(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self._skills.values()]
