"""omnibrain-skill CLI — scaffold, test, and publish Skill packages.

Usage:
    omnibrain-skill init <name> [--category <cat>] [--triggers <t>]
    omnibrain-skill test [<skill-dir>]
    omnibrain-skill publish <skill-dir>          (coming soon)

This module implements the "Build a Skill in 30 min" developer experience
described in SKILL-PROTOCOL.md §10.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════════════════════

_SKILL_YAML = """\
name: {name}
version: 0.1.0
description: "{description}"
author: {author}
icon: "{icon}"
category: {category}

triggers:
{triggers}

permissions: [{permissions}]

settings:
  example_setting:
    type: string
    default: ""
    description: "An example setting — replace or remove"

handlers:
{handlers}

requires_core: ">=0.1.0"
"""

_POLL_HANDLER = '''\
"""
{title} — Schedule handler (poll.py).

Runs on the configured schedule (see skill.yaml triggers.schedule).
"""

from __future__ import annotations


async def handle(ctx) -> dict:
    """Periodic task — fetch data, detect changes, notify user.

    Args:
        ctx: SkillContext sandbox with permission-gated methods.

    Returns:
        dict summary of what happened during this invocation.
    """
    # TODO: Implement your periodic logic here.
    #
    # Available ctx methods (depends on declared permissions):
    #   await ctx.memory_search(query, limit=10)
    #   await ctx.memory_store(text, source=..., metadata={{...}})
    #   await ctx.notify(message, level="fyi")
    #   await ctx.propose_action(type=..., title=..., description=...)
    #   await ctx.get_data(key, default=None)   # skill-local storage
    #   await ctx.set_data(key, value)
    #   await ctx.llm_complete(prompt, task_type="reasoning")
    #   ctx.user_preferences, ctx.user_name, ctx.user_timezone

    return {{"status": "ok"}}
'''

_ASK_HANDLER = '''\
"""
{title} — Ask handler (ask.py).

Triggered when the user asks a question matching the on_ask regex.
"""

from __future__ import annotations


async def handle(ctx, query: str) -> dict:
    """Answer a user question.

    Args:
        ctx: SkillContext sandbox.
        query: The user's natural-language question.

    Returns:
        dict with at minimum an "answer" key.
    """
    # TODO: Implement your question-answering logic here.
    return {{"answer": f"Skill {name!r} received: {{query}}"}}
'''

_EVENT_HANDLER = '''\
"""
{title} — Event handler (event.py).

Triggered by internal events matching on_event in skill.yaml.
"""

from __future__ import annotations


async def handle(ctx, event: dict) -> dict:
    """React to a system event.

    Args:
        ctx: SkillContext sandbox.
        event: The event payload dict.

    Returns:
        dict summary.
    """
    # TODO: Implement your event-reaction logic here.
    return {{"status": "handled", "event_type": event.get("type", "unknown")}}
'''

_README = """\
# {title}

> {description}

## Quick Start

1. Copy this directory into `skills/` in your OmniBrain installation.
2. Restart OmniBrain — the skill is loaded automatically.
3. Configure settings via the Settings page.

## Handlers

| Handler | Trigger | Description |
|---------|---------|-------------|
{handler_table}

## Permissions

{permissions_list}

## Development

```bash
# Run tests
omnibrain-skill test {name}

# Or via pytest directly
pytest {name}/tests/
```
"""

_TEST_HANDLERS = '''\
"""Tests for {title} handlers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from omnibrain.skill_context import SkillContext


def _make_ctx(permissions: set[str] | None = None):
    perms = permissions or {{{permissions_set}}}
    return SkillContext(
        skill_name="{name}",
        permissions=perms,
    )


class TestPollHandler:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        skill_path = Path(__file__).parent.parent
        fn = _load_handler(skill_path, "handlers/poll.py")
        assert fn is not None, "Could not load poll handler"
        return fn

    @pytest.mark.asyncio
    async def test_poll_returns_dict(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(return_value=None)
        ctx.set_data = AsyncMock()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.notify = AsyncMock()
        ctx.propose_action = AsyncMock()
        result = await handler(ctx)
        assert isinstance(result, dict)


class TestAskHandler:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        skill_path = Path(__file__).parent.parent
        fn = _load_handler(skill_path, "handlers/ask.py")
        assert fn is not None, "Could not load ask handler"
        return fn

    @pytest.mark.asyncio
    async def test_ask_returns_answer(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(return_value=None)
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.llm_complete = AsyncMock(return_value=None)
        ctx.has_permission = MagicMock(return_value=False)
        result = await handler(ctx, "test query")
        assert "answer" in result
'''

# ═══════════════════════════════════════════════════════════════════════════
# Default Configurations
# ═══════════════════════════════════════════════════════════════════════════

CATEGORIES = [
    "communication", "productivity", "analytics", "automation",
    "health", "finance", "development", "other",
]

ICONS = {
    "communication": "💬",
    "productivity": "⚡",
    "analytics": "📊",
    "automation": "🤖",
    "health": "🏥",
    "finance": "💰",
    "development": "🛠️",
    "other": "🔧",
}


# ═══════════════════════════════════════════════════════════════════════════
# Core Logic
# ═══════════════════════════════════════════════════════════════════════════


def _slugify(name: str) -> str:
    """Convert name to a valid skill slug (lowercase kebab-case)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "my-skill"


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").title()


def init_skill(
    name: str,
    *,
    output_dir: Path | None = None,
    category: str = "other",
    triggers: list[str] | None = None,
    permissions: list[str] | None = None,
    author: str = "your-name",
    with_event_handler: bool = False,
) -> Path:
    """Scaffold a new Skill directory with manifest, handlers, tests, and README.

    Returns the created directory path.
    """
    slug = _slugify(name)
    title = _title_from_slug(slug)
    base = (output_dir or Path.cwd()) / slug
    handlers_dir = base / "handlers"
    tests_dir = base / "tests"

    if base.exists():
        raise FileExistsError(f"Directory already exists: {base}")

    handlers_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    # Determine triggers
    trigger_lines = []
    handler_entries = []
    handler_table_rows = []

    if triggers:
        for t in triggers:
            trigger_lines.append(f'  - {t}')
    else:
        trigger_lines = [
            '  - schedule: "every 1h"',
            f'  - on_ask: "(?i)({slug.replace("-", "|")})"',
        ]

    # Determine handlers
    handler_entries.append('  schedule: "handlers/poll.py"')
    handler_entries.append('  on_ask: "handlers/ask.py"')
    handler_table_rows.append("| poll.py | schedule | Periodic task |")
    handler_table_rows.append("| ask.py | on_ask | User question |")

    if with_event_handler:
        trigger_lines.append(f'  - on_event: "{slug}_event"')
        handler_entries.append('  on_event: "handlers/event.py"')
        handler_table_rows.append("| event.py | on_event | System event |")

    # Determine permissions
    perms = permissions or ["read_memory", "notify", "llm_access"]
    perms_str = ", ".join(perms)
    perms_set_str = ", ".join(f'"{p}"' for p in perms)

    icon = ICONS.get(category, "🔧")
    description = f"{title} skill for OmniBrain"

    # Write skill.yaml
    (base / "skill.yaml").write_text(
        _SKILL_YAML.format(
            name=slug,
            description=description,
            author=author,
            icon=icon,
            category=category,
            triggers="\n".join(trigger_lines),
            permissions=perms_str,
            handlers="\n".join(handler_entries),
        )
    )

    # Write handlers
    (handlers_dir / "poll.py").write_text(
        _POLL_HANDLER.format(title=title)
    )
    (handlers_dir / "ask.py").write_text(
        _ASK_HANDLER.format(title=title, name=slug)
    )
    if with_event_handler:
        (handlers_dir / "event.py").write_text(
            _EVENT_HANDLER.format(title=title)
        )

    # Write tests
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_handlers.py").write_text(
        _TEST_HANDLERS.format(
            title=title,
            name=slug,
            permissions_set=perms_set_str,
        )
    )

    # Write README
    (base / "README.md").write_text(
        _README.format(
            title=title,
            description=description,
            name=slug,
            handler_table="\n".join(handler_table_rows),
            permissions_list="\n".join(f"- `{p}`" for p in perms),
        )
    )

    return base


# ═══════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="omnibrain-skill",
        description="OmniBrain Skill developer toolkit",
    )
    sub = parser.add_subparsers(dest="command")

    # --- init ---
    p_init = sub.add_parser("init", help="Scaffold a new Skill")
    p_init.add_argument("name", help="Skill name (will be slugified)")
    p_init.add_argument(
        "--category", choices=CATEGORIES, default="other",
        help="Skill category (default: other)",
    )
    p_init.add_argument(
        "--author", default="your-name",
        help="Author name for the manifest",
    )
    p_init.add_argument(
        "--permissions", nargs="+",
        help="Permissions list (default: read_memory notify llm_access)",
    )
    p_init.add_argument(
        "--with-event-handler", action="store_true",
        help="Include an on_event handler",
    )
    p_init.add_argument(
        "--output-dir", type=Path, default=None,
        help="Parent directory for the skill (default: cwd)",
    )

    # --- test ---
    p_test = sub.add_parser("test", help="Run tests for a Skill")
    p_test.add_argument(
        "skill_dir", nargs="?", default=".",
        help="Path to skill directory (default: current directory)",
    )

    # --- publish ---
    sub.add_parser("publish", help="Publish a Skill (coming soon)")

    args = parser.parse_args(argv)

    if args.command == "init":
        try:
            path = init_skill(
                args.name,
                category=args.category,
                author=args.author,
                permissions=args.permissions,
                with_event_handler=args.with_event_handler,
                output_dir=args.output_dir,
            )
            print(f"✅ Skill scaffolded at {path}")
            print(f"   Next: cd {path.name} && edit handlers/poll.py")
            return 0
        except FileExistsError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1

    elif args.command == "test":
        import subprocess
        skill_path = Path(args.skill_dir).resolve()
        tests_dir = skill_path / "tests"
        if not tests_dir.exists():
            print(f"❌ No tests/ directory in {skill_path}", file=sys.stderr)
            return 1
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests_dir), "-v"],
            cwd=str(skill_path.parent),
        )
        return result.returncode

    elif args.command == "publish":
        print("⏳ Publish is coming soon. For now, share your skill directory manually.")
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
