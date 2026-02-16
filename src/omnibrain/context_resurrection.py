"""
OmniBrain — Context Resurrection (Day 24-25)

Tracks project context and resurrects it when the user returns
to an old project. Answers "Where was I?" automatically.

Architecture:
    ProjectContext
    ├── record_activity()      — log file/branch/action for a project
    ├── get_project_context()  — current state of a project
    ├── detect_return()        — was this project dormant? → resurrect
    └── generate_resurrection()— summary: where you left off, what changed

This is Magic Moment #3 from the manifesto:
    "Opened a project I abandoned 3 weeks ago.
     OmniBrain remembered exactly where I was stuck.
     And it found the solution."
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from omnibrain.db import OmniBrainDB
from omnibrain.memory import MemoryManager

logger = logging.getLogger("omnibrain.context_resurrection")


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ProjectActivity:
    """A single activity record for a project."""

    project: str           # project directory name or identifier
    action: str            # file_open, file_edit, branch_switch, build, run, search, etc.
    detail: str = ""       # specific file, branch name, search query, etc.
    timestamp: str = ""    # ISO format
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "action": self.action,
            "detail": self.detail,
            "timestamp": self.timestamp or datetime.now().isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ProjectSnapshot:
    """Current state of a project — what OmniBrain knows about it."""

    project: str
    last_active: str = ""
    branch: str = ""
    last_files: list[str] = field(default_factory=list)
    recent_actions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    days_inactive: int = 0
    activity_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "last_active": self.last_active,
            "branch": self.branch,
            "last_files": self.last_files[:10],
            "recent_actions": self.recent_actions[:10],
            "blockers": self.blockers,
            "notes": self.notes,
            "days_inactive": self.days_inactive,
            "activity_count": self.activity_count,
        }


@dataclass
class ResurrectionSummary:
    """The "Where was I?" summary shown when returning to a project."""

    project: str
    days_since_last: int
    last_branch: str
    last_files: list[str]
    blockers: list[str]
    what_changed: list[str]
    related_conversations: list[str]
    suggested_next_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "days_since_last": self.days_since_last,
            "last_branch": self.last_branch,
            "last_files": self.last_files,
            "blockers": self.blockers,
            "what_changed": self.what_changed,
            "related_conversations": self.related_conversations,
            "suggested_next_steps": self.suggested_next_steps,
        }

    def format_text(self) -> str:
        """Format as readable text for display."""
        lines = [
            f"📂 Project: {self.project}",
            f"⏰ Last active: {self.days_since_last} day(s) ago",
        ]
        if self.last_branch:
            lines.append(f"🌿 Branch: {self.last_branch}")
        if self.last_files:
            lines.append(f"📄 Last files: {', '.join(self.last_files[:5])}")
        if self.blockers:
            lines.append("\n🚧 Blockers:")
            for b in self.blockers:
                lines.append(f"  • {b}")
        if self.what_changed:
            lines.append("\n🔄 What changed while you were away:")
            for c in self.what_changed:
                lines.append(f"  • {c}")
        if self.related_conversations:
            lines.append("\n💬 Related conversations:")
            for c in self.related_conversations:
                lines.append(f"  • {c}")
        if self.suggested_next_steps:
            lines.append("\n✅ Suggested next steps:")
            for s in self.suggested_next_steps:
                lines.append(f"  • {s}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Context Tracker
# ═══════════════════════════════════════════════════════════════════════════


class ContextTracker:
    """Tracks and resurrects project context.

    Records every project activity, detects when a user returns
    to a dormant project, and generates a resurrection summary.

    Usage:
        tracker = ContextTracker(db, memory)

        # Record activities
        tracker.record_activity("omnibrain", "file_edit", "src/main.py")
        tracker.record_activity("omnibrain", "branch_switch", "feature/api")
        tracker.record_activity("omnibrain", "blocker_noted", "ChromaDB incompatible with 3.14")

        # Later, detect return
        resurrection = tracker.detect_return("omnibrain")
        if resurrection:
            print(resurrection.format_text())
    """

    # Activity types that indicate active work
    ACTIVE_ACTIONS = {"file_edit", "file_open", "build", "run", "test", "commit", "push"}
    # Minimum days of inactivity to trigger resurrection
    DEFAULT_DORMANT_DAYS = 3

    def __init__(
        self,
        db: OmniBrainDB,
        memory: MemoryManager | None = None,
        dormant_days: int = 3,
    ):
        self._db = db
        self._memory = memory
        self._dormant_days = dormant_days

    # ── Recording ──

    def record_activity(
        self,
        project: str,
        action: str,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Record a project activity. Returns the event ID."""
        activity = ProjectActivity(
            project=project,
            action=action,
            detail=detail,
            metadata=metadata or {},
        )

        event_id = self._db.insert_event(
            source=f"project:{project}",
            event_type=f"project_activity",
            title=f"{action}: {detail}" if detail else action,
            content=json.dumps(activity.to_dict()),
            metadata={
                "project": project,
                "action": action,
                "detail": detail,
                **(metadata or {}),
            },
        )
        logger.debug(f"Recorded activity for {project}: {action} {detail}")
        return event_id

    def record_blocker(self, project: str, description: str) -> int:
        """Record a blocker for a project."""
        return self.record_activity(
            project, "blocker_noted", description,
            metadata={"is_blocker": True},
        )

    def record_note(self, project: str, note: str) -> int:
        """Record a note for a project."""
        return self.record_activity(
            project, "note", note,
            metadata={"is_note": True},
        )

    def record_branch(self, project: str, branch: str) -> int:
        """Record a branch switch."""
        return self.record_activity(project, "branch_switch", branch)

    # ── Querying ──

    def get_project_context(self, project: str, days: int = 90) -> ProjectSnapshot:
        """Get the current context snapshot for a project."""
        since = datetime.now() - timedelta(days=days)
        events = self._db.get_events(
            source=f"project:{project}",
            since=since,
            limit=200,
        )

        if not events:
            return ProjectSnapshot(project=project)

        # Extract info
        last_active = ""
        branch = ""
        files: list[str] = []
        actions: list[str] = []
        blockers: list[str] = []
        notes: list[str] = []

        for ev in events:
            ts = ev.get("timestamp", "")
            if ts > last_active:
                last_active = ts

            metadata = _safe_json(ev.get("metadata", "{}"))
            action = metadata.get("action", "")
            detail = metadata.get("detail", "")

            if action == "branch_switch" and detail:
                branch = detail
            elif action in ("file_edit", "file_open") and detail:
                if detail not in files:
                    files.append(detail)
            elif action == "blocker_noted" and detail:
                blockers.append(detail)
            elif action == "note" and detail:
                notes.append(detail)

            actions.append(f"{action}: {detail}" if detail else action)

        days_inactive = 0
        if last_active:
            try:
                last_dt = datetime.fromisoformat(last_active)
                days_inactive = (datetime.now() - last_dt).days
            except (ValueError, TypeError):
                pass

        return ProjectSnapshot(
            project=project,
            last_active=last_active,
            branch=branch,
            last_files=files[:10],
            recent_actions=actions[:10],
            blockers=blockers,
            notes=notes,
            days_inactive=days_inactive,
            activity_count=len(events),
        )

    def get_all_projects(self) -> list[str]:
        """Get all tracked projects."""
        events = self._db.get_events(limit=1000)
        projects: set[str] = set()
        for ev in events:
            source = ev.get("source", "")
            if source.startswith("project:"):
                projects.add(source[len("project:"):])
        return sorted(projects)

    def get_dormant_projects(self, dormant_days: int | None = None) -> list[ProjectSnapshot]:
        """Get projects that have been inactive for N+ days."""
        threshold = dormant_days or self._dormant_days
        all_projects = self.get_all_projects()
        dormant = []
        for project in all_projects:
            ctx = self.get_project_context(project)
            if ctx.days_inactive >= threshold:
                dormant.append(ctx)
        dormant.sort(key=lambda s: s.days_inactive, reverse=True)
        return dormant

    # ── Resurrection ──

    def detect_return(self, project: str) -> ResurrectionSummary | None:
        """Check if this is a return to a dormant project.

        Returns a ResurrectionSummary if the project was dormant,
        or None if the project is recently active.
        """
        ctx = self.get_project_context(project)

        if ctx.days_inactive < self._dormant_days:
            return None

        return self.generate_resurrection(project, ctx)

    def generate_resurrection(
        self,
        project: str,
        ctx: ProjectSnapshot | None = None,
    ) -> ResurrectionSummary:
        """Generate a full resurrection summary for a project."""
        if ctx is None:
            ctx = self.get_project_context(project)

        # What changed: look for events mentioning this project since last_active
        what_changed = self._find_changes_since(project, ctx.last_active)

        # Related conversations from memory
        related = self._find_related_conversations(project, ctx)

        # Suggested next steps
        next_steps = self._suggest_next_steps(ctx)

        return ResurrectionSummary(
            project=project,
            days_since_last=ctx.days_inactive,
            last_branch=ctx.branch,
            last_files=ctx.last_files,
            blockers=ctx.blockers,
            what_changed=what_changed,
            related_conversations=related,
            suggested_next_steps=next_steps,
        )

    # ── Internal Helpers ──

    def _find_changes_since(self, project: str, since_iso: str) -> list[str]:
        """Find relevant changes since the project was last active."""
        changes: list[str] = []

        if not self._memory or not since_iso:
            return changes

        # Search memory for project-related changes
        results = self._memory.search(project, max_results=10, time_range_days=90)
        for doc in results:
            if doc.timestamp > since_iso:
                changes.append(f"[{doc.source_type}] {doc.text[:100]}")

        return changes[:5]

    def _find_related_conversations(
        self,
        project: str,
        ctx: ProjectSnapshot,
    ) -> list[str]:
        """Find conversations related to this project."""
        if not self._memory:
            return []

        # Search for project name + blockers + key files
        search_terms = [project]
        search_terms.extend(ctx.blockers[:2])

        conversations: list[str] = []
        seen: set[str] = set()

        for term in search_terms:
            if not term:
                continue
            results = self._memory.search(term, max_results=5, time_range_days=90)
            for doc in results:
                if doc.source_type in ("email", "telegram") and doc.id not in seen:
                    seen.add(doc.id)
                    conversations.append(f"{doc.source}: {doc.text[:100]}")

        return conversations[:5]

    def _suggest_next_steps(self, ctx: ProjectSnapshot) -> list[str]:
        """Generate suggested next steps based on context."""
        steps: list[str] = []

        if ctx.blockers:
            steps.append(f"Resolve blocker: {ctx.blockers[0]}")

        if ctx.last_files:
            steps.append(f"Continue working on {ctx.last_files[0]}")

        if ctx.branch and ctx.branch != "main" and ctx.branch != "master":
            steps.append(f"Review changes on branch '{ctx.branch}'")

        if ctx.notes:
            steps.append(f"Review note: {ctx.notes[-1][:60]}")

        if not steps:
            steps.append("Review project status")

        return steps


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _safe_json(raw: str | dict) -> dict:
    """Safely parse JSON."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}
